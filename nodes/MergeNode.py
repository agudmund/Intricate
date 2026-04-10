#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/MergeNode.py MergeNode class
-Lists connected AudioNodes in sequential order as a merge staging area for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QGraphicsProxyWidget, QAbstractItemView

from nodes.BaseNode import BaseNode
from data.MergeNodeData import MergeNodeData
from pretty_widgets.graphics.Theme import Theme


_PAD = 8.0
_DRAG_THRESHOLD = 10  # px before a click becomes a drag


class _DraggableListWidget(QListWidget):
    """QListWidget with manual drag-to-reorder that works inside QGraphicsProxyWidget.

    Qt's InternalMove drag-drop mode breaks inside proxy widgets because the
    proxy intercepts the drag events. This subclass tracks mouse press/move/release
    directly and moves items programmatically — no QDrag object needed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_row = -1
        self._drag_active = False
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                self._drag_row = self.row(item)
                self._drag_start_pos = event.pos()
                self._drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_row >= 0 and self._drag_start_pos is not None:
            if not self._drag_active:
                dist = (event.pos() - self._drag_start_pos).manhattanLength()
                if dist >= _DRAG_THRESHOLD:
                    self._drag_active = True
            if self._drag_active:
                target_item = self.itemAt(event.pos())
                if target_item:
                    target_row = self.row(target_item)
                    if target_row != self._drag_row:
                        item = self.takeItem(self._drag_row)
                        self.insertItem(target_row, item)
                        self.setCurrentItem(item)
                        self._drag_row = target_row
                return  # don't pass to super during drag
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_row = -1
        self._drag_active = False
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


class MergeNode(BaseNode):
    """
    Merge staging node — displays connected AudioNodes as a numbered list.

    Connect AudioNodes via ports. An embedded QListWidget shows their
    captions (or filenames) with drag-and-drop reordering. The play
    button plays the list in the displayed order.
    """

    _has_depth_toggle = True

    def __init__(self, data: MergeNodeData | None = None):
        if data is None:
            data = MergeNodeData()
        super().__init__(data)

        self._playing = False
        self._play_queue: list = []
        self._current_index = 0

        # ── Embedded list widget ──────────────────────────────────────────────
        self._list = _DraggableListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setFrameShape(QListWidget.NoFrame)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._list_context_menu)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: {Theme.healthFontSizeLabel}pt;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 2px 4px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background: {Theme.primaryBorder};
            }}
            QListWidget::item:hover {{
                background: {Theme.backDrop};
            }}
            QScrollBar:vertical {{
                width: 4px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.primaryBorder};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._list_proxy = QGraphicsProxyWidget(self)
        self._list_proxy.setWidget(self._list)
        self._position_list()

        # Refresh the list whenever connections might have changed
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(500)
        self._refresh_timer.setSingleShot(False)
        self._refresh_timer.timeout.connect(self._sync_list)
        self._refresh_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # LIST WIDGET
    # ─────────────────────────────────────────────────────────────────────────

    def _position_list(self) -> None:
        """Position the list proxy in the body area below the title."""
        r = self.rect()
        body_y = self._body_top()
        self._list_proxy.setGeometry(QRectF(
            r.x() + _PAD,
            r.y() + body_y,
            r.width() - _PAD * 2,
            r.height() - body_y - _PAD,
        ))

    def _sync_list(self) -> None:
        """Refresh the list to match connected AudioNodes.

        Adds new connections, removes stale ones, preserves user reordering.
        Items store the AudioNode's uuid in their data role so we can
        map list order back to nodes for playback.
        """
        audio_nodes = self._get_connected_audio_nodes()
        connected_uuids = {n.data.uuid for n in audio_nodes}
        uuid_to_node = {n.data.uuid: n for n in audio_nodes}

        # Existing items in the list (by uuid)
        existing_uuids = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            existing_uuids.add(item.data(Qt.UserRole))

        # Remove items whose nodes are no longer connected
        stale = existing_uuids - connected_uuids
        if stale:
            for i in range(self._list.count() - 1, -1, -1):
                if self._list.item(i).data(Qt.UserRole) in stale:
                    self._list.takeItem(i)

        # Add new connections that aren't in the list yet
        new = connected_uuids - existing_uuids
        for node in audio_nodes:
            if node.data.uuid in new:
                label = self._label_for(node)
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, node.data.uuid)
                self._list.addItem(item)

        # Update labels for existing items (caption may have changed)
        for i in range(self._list.count()):
            item = self._list.item(i)
            uid = item.data(Qt.UserRole)
            if uid in uuid_to_node:
                new_label = self._label_for(uuid_to_node[uid])
                if item.text() != new_label:
                    item.setText(new_label)

    @staticmethod
    def _label_for(node) -> str:
        """Display label for an AudioNode/VideoNode — caption or filename."""
        from nodes.VideoNode import VideoNode
        prefix = "\U0001f3ac " if isinstance(node, VideoNode) else ""  # 🎬
        if node.data.caption:
            return f"{prefix}{node.data.caption}"
        if node.data.source_path:
            return f"{prefix}{Path(node.data.source_path).stem}"
        return f"{prefix}untitled"

    def _list_context_menu(self, pos) -> None:
        """Right-click menu on list items — Move Up / Move Down."""
        item = self._list.itemAt(pos)
        if not item:
            return
        row = self._list.row(item)
        from pretty_widgets.PrettyMenu import menu as pretty_menu
        ctx = pretty_menu()
        if row > 0:
            up = ctx.addAction("Move Up")
            up.triggered.connect(lambda: self._move_item(row, row - 1))
        if row < self._list.count() - 1:
            down = ctx.addAction("Move Down")
            down.triggered.connect(lambda: self._move_item(row, row + 1))
        ctx.exec(self._list.viewport().mapToGlobal(pos))

    def _move_item(self, from_row: int, to_row: int) -> None:
        """Move a list item from one row to another."""
        item = self._list.takeItem(from_row)
        self._list.insertItem(to_row, item)
        self._list.setCurrentItem(item)

    def _get_ordered_audio_nodes(self) -> list:
        """Return AudioNodes in the list widget's current display order."""
        audio_nodes = self._get_connected_audio_nodes()
        uuid_to_node = {n.data.uuid: n for n in audio_nodes}
        ordered = []
        for i in range(self._list.count()):
            uid = self._list.item(i).data(Qt.UserRole)
            if uid in uuid_to_node:
                ordered.append(uuid_to_node[uid])
        return ordered

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTON STRIP
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import EmojiButton
        super()._build_buttons()

        self._play_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u2016" if self._playing else "\u25b6",  # ‖ / ▶
            set_emoji=lambda _: self._toggle_playback(),
        )
        self._play_btn.setToolTip("Play / Pause")
        self._buttons.append(self._play_btn)

        self._combine_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001f4be",   # 💾
            set_emoji=lambda _: self._combine_to_file(),
        )
        self._combine_btn.setToolTip("Combine sequential (crossfade)")
        self._buttons.append(self._combine_btn)

        self._overlay_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001f3b6",   # 🎶
            set_emoji=lambda _: self._overlay_to_file(),
        )
        self._overlay_btn.setToolTip("Overlay mix (stack audio layers)")
        self._buttons.append(self._overlay_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # SEQUENTIAL PLAYBACK
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_playback(self) -> None:
        """Play connected AudioNodes sequentially in the list's display order."""
        if self._playing:
            self._stop_sequence()
            return

        # Use the list widget order, not connection order
        ordered = self._get_ordered_audio_nodes()
        self._play_queue = [n for n in ordered if hasattr(n, '_player')]
        if not self._play_queue:
            return

        self._playing = True
        self._current_index = 0
        self._play_current()
        self._play_btn.update()
        self.update()

    def _play_current(self) -> None:
        """Start playing the current node in the queue."""
        if self._current_index >= len(self._play_queue):
            self._stop_sequence()
            return

        node = self._play_queue[self._current_index]
        from PySide6.QtMultimedia import QMediaPlayer

        node._player.setPosition(0)
        node._player.mediaStatusChanged.connect(self._on_media_status_changed)
        node._player.play()
        self.update()

    def _on_media_status_changed(self, status) -> None:
        """Advance to the next track when the current one finishes."""
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._advance_sequence()

    def _advance_sequence(self) -> None:
        """Disconnect current track and play the next one."""
        if self._current_index < len(self._play_queue):
            node = self._play_queue[self._current_index]
            try:
                node._player.mediaStatusChanged.disconnect(self._on_media_status_changed)
            except RuntimeError:
                pass
        self._current_index += 1
        self._play_current()

    def _stop_sequence(self) -> None:
        """Stop playback and reset the queue."""
        if self._current_index < len(self._play_queue):
            node = self._play_queue[self._current_index]
            if hasattr(node, '_player'):
                node._player.pause()
                try:
                    node._player.mediaStatusChanged.disconnect(self._on_media_status_changed)
                except RuntimeError:
                    pass
        self._playing = False
        self._play_queue = []
        self._current_index = 0
        self._play_btn.update()
        self.update()

    _CROSSFADE_S = 0.5   # default crossfade duration in seconds

    def _combine_to_file(self) -> None:
        """Merge all listed audio/hold nodes with crossfade using ffmpeg.

        AudioNodes contribute their source file. AudioHoldNodes contribute
        inline silence via anullsrc — no temp files, no disk I/O for holds.
        """
        import subprocess as _sp
        from nodes.AudioHoldNode import AudioHoldNode
        from pretty_widgets.utils.logger import setup_logger
        _log = setup_logger("merge")

        ordered = self._get_ordered_audio_nodes()
        if len(ordered) < 2:
            return

        # Build input args and track which index is a hold
        inputs = []
        input_meta = []   # list of (index, is_hold, hold_seconds)
        idx = 0
        src_dir = None
        ext = ".wav"
        for node in ordered:
            if isinstance(node, AudioHoldNode):
                dur = node.data.hold_seconds
                inputs.extend(["-f", "lavfi", "-t", f"{dur:.3f}",
                               "-i", f"anullsrc=r=44100:cl=stereo"])
                input_meta.append((idx, True, dur))
            else:
                p = node.data.source_path
                if not p or not Path(p).exists():
                    continue
                inputs.extend(["-i", p])
                input_meta.append((idx, False, 0))
                if src_dir is None:
                    src_dir = Path(p).parent
                    ext = Path(p).suffix
            idx += 1

        if len(input_meta) < 2 or src_dir is None:
            return

        stem = self.data.title or "merged"
        out  = src_dir / f"{stem}{ext}"
        counter = 2
        while out.exists():
            out = src_dir / f"{stem}_{counter}{ext}"
            counter += 1

        cf = self._CROSSFADE_S

        # Build acrossfade filter chain
        filters = []
        prev = f"[{input_meta[0][0]}]"
        for i in range(1, len(input_meta)):
            tag = f"[a{i:02d}]"
            inp = f"[{input_meta[i][0]}]"
            filters.append(
                f"{prev}{inp}acrossfade=d={cf}:c1=tri:c2=tri{tag}"
            )
            prev = tag

        filter_str = ";".join(filters)

        try:
            _sp.run([
                "ffmpeg", "-y", *inputs,
                "-filter_complex", filter_str,
                "-map", prev, str(out),
            ], capture_output=True, check=True)
        except Exception as e:
            _log.warning(f"[MergeNode] combine failed: {e}")
            return

        # Spawn a new AudioNode with the combined file
        scene = self.scene()
        if not scene or not hasattr(scene, 'add_audio_node'):
            return

        from PySide6.QtCore import QPointF
        my_pos = self.pos()
        node = scene.add_audio_node(pos=my_pos + QPointF(0, self.rect().height() + 30))
        node.load_from_path(str(out))
        _log.info(f"[MergeNode] combined {len(input_meta)} sources → {out.name}")

    def _overlay_to_file(self) -> None:
        """Mix all listed audio sources into a single file, layered on top of
        each other at their per-node volume levels.

        VideoNodes have their audio extracted first via ffmpeg.  Each source
        is scaled by its data.volume (0-100) using the ffmpeg ``volume``
        filter, then all streams are stacked with ``amix``.
        """
        import subprocess as _sp
        import tempfile
        from nodes.AudioNode import AudioNode
        from nodes.AudioHoldNode import AudioHoldNode
        from nodes.VideoNode import VideoNode
        from pretty_widgets.utils.logger import setup_logger
        _log = setup_logger("merge")

        ordered = self._get_ordered_audio_nodes()
        if len(ordered) < 2:
            return

        # ── Collect source paths and volume scalars ──────────────────────
        sources: list[tuple[str, float]] = []   # (wav_path, volume_0_to_1)
        temp_files: list[str] = []              # cleanup after merge
        src_dir = None

        for node in ordered:
            if isinstance(node, AudioHoldNode):
                continue
            p = node.data.source_path
            if not p or not Path(p).exists():
                continue

            vol = node.data.volume / 100.0

            if isinstance(node, VideoNode):
                # Extract audio track to a temp wav
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False, prefix="intricate_mix_",
                )
                tmp.close()
                try:
                    _sp.run([
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-i", p, "-vn",
                        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                        tmp.name,
                    ], capture_output=True, check=True)
                except Exception as e:
                    _log.warning("[MergeNode] extract audio failed for %s: %s", p, e)
                    continue
                sources.append((tmp.name, vol))
                temp_files.append(tmp.name)
            else:
                # AudioNode — use source directly
                sources.append((p, vol))

            if src_dir is None:
                src_dir = Path(p).parent

        if len(sources) < 2 or src_dir is None:
            self._cleanup_temps(temp_files)
            return

        # ── Build ffmpeg command ─────────────────────────────────────────
        # Inputs
        inputs = []
        for path, _ in sources:
            inputs.extend(["-i", path])

        # Filter: scale each input by its volume, then amix them together
        n = len(sources)
        vol_filters = []
        mix_inputs  = []
        for i, (_, vol) in enumerate(sources):
            tag = f"[v{i}]"
            vol_filters.append(f"[{i}]volume={vol:.3f}{tag}")
            mix_inputs.append(tag)

        amix_in  = "".join(mix_inputs)
        # duration=longest keeps playing until the longest track ends;
        # normalize=0 prevents amix from auto-scaling (we set volumes explicitly)
        amix     = f"{amix_in}amix=inputs={n}:duration=longest:normalize=0[out]"
        filter_str = ";".join(vol_filters) + ";" + amix

        stem = self.data.title or "overlay_mix"
        out  = src_dir / f"{stem}.wav"
        counter = 2
        while out.exists():
            out = src_dir / f"{stem}_{counter}.wav"
            counter += 1

        try:
            _sp.run([
                "ffmpeg", "-y", *inputs,
                "-filter_complex", filter_str,
                "-map", "[out]",
                "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                str(out),
            ], capture_output=True, check=True)
        except Exception as e:
            _log.warning("[MergeNode] overlay mix failed: %s", e)
            self._cleanup_temps(temp_files)
            return

        self._cleanup_temps(temp_files)

        # Spawn AudioNode with the result
        scene = self.scene()
        if not scene or not hasattr(scene, 'add_audio_node'):
            return
        from PySide6.QtCore import QPointF
        node = scene.add_audio_node(
            pos=self.pos() + QPointF(0, self.rect().height() + 30),
        )
        node.load_from_path(str(out))
        _log.info("[MergeNode] overlay mixed %d sources → %s", n, out.name)

    @staticmethod
    def _cleanup_temps(paths: list[str]) -> None:
        """Remove temporary extracted audio files."""
        import os
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTED AUDIO NODES
    # ─────────────────────────────────────────────────────────────────────────

    def _get_connected_audio_nodes(self) -> list:
        """Return AudioNodes, AudioHoldNodes, and VideoNodes connected to this node."""
        from nodes.AudioNode import AudioNode
        from nodes.AudioHoldNode import AudioHoldNode
        from nodes.VideoNode import VideoNode
        audio_nodes = []
        for conn in self.connections:
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other and isinstance(other, (AudioNode, AudioHoldNode, VideoNode)):
                audio_nodes.append(other)
        return audio_nodes

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """Draw title via BaseNode — list widget handles the body."""
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if hasattr(self, '_list_proxy'):
            self._position_list()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        # Disconnect from ALL queued AudioNode players, not just the current one
        for node in self._play_queue:
            if hasattr(node, '_player'):
                try:
                    node._player.mediaStatusChanged.disconnect(self._on_media_status_changed)
                except RuntimeError:
                    pass
        self._stop_sequence()

        self._refresh_timer.stop()
        try:
            self._refresh_timer.timeout.disconnect(self._sync_list)
        except RuntimeError:
            pass

        if self._list_proxy:
            self._list_proxy.hide()
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'MergeNode':
        return MergeNode(MergeNodeData.from_dict(data))
