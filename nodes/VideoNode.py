#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/VideoNode.py VideoNode class
-Renders video with full playback inside the canvas via QMediaPlayer for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QFileDialog, QGraphicsItem
)
from widgets.PrettyMenu import StyledLineEdit as QLineEdit
from PySide6.QtCore import Qt, QRectF, QPointF, QUrl, QSizeF
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QPainterPath, QFont
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame

from nodes.BaseNode import BaseNode
from data.VideoNodeData import VideoNodeData
from graphics.Theme import Theme
import utils.settings as settings
from utils.logger import setup_logger

logger = setup_logger("video")


# Layout constants
CAPTION_HEIGHT   = 28.0     # Height of the caption band at the bottom
PROGRESS_HEIGHT  = 14.0     # Height of the scrub/progress bar
VIDEO_PADDING    = 6.0      # Inset on all sides
CLIP_RADIUS_MIN  = 2.0      # Minimum clip radius inside the padding

_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv", ".m4v"}


def _fmt_time(ms: int) -> str:
    """Format milliseconds as m:ss."""
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class VideoNode(BaseNode):
    """
    Renders video with full playback inside the node body.

    Layout (top to bottom inside the node body):
        ┌─────────────────────────────────┐
        │  VIDEO_PADDING                  │
        │  ┌───────────────────────────┐  │
        │  │                           │  │
        │  │     video frame area      │  │
        │  │                           │  │
        │  └───────────────────────────┘  │
        │  [ progress / scrub bar ]       │
        │  caption band                   │
        └─────────────────────────────────┘

    Interaction zones (routed in mouseDoubleClickEvent):
        Caption band  → activate inline QLineEdit editor
        Video area    → open file browser (when empty) or toggle play/pause
        Progress bar  → scrub to position

    OS drag and drop:
        Handled by IntricateView.dropEvent — video files dragged from Explorer
        land on the view, get mapped to scene coordinates, and a VideoNode
        receives the path via load_from_path().
    """

    _show_ports_btn = True

    def __init__(self, data: VideoNodeData | None = None):
        if data is None:
            data = VideoNodeData()
        super().__init__(data)

        # ── Current frame pixmap ──────────────────────────────────────────────
        self._frame_pixmap: QPixmap | None = None
        self._scaled_cache: QPixmap | None = None
        self._scaled_cache_size: tuple[int, int] | None = None

        # ── Media player ──────────────────────────────────────────────────────
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._sink   = QVideoSink()

        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._sink)
        self._audio.setVolume(data.volume / 100.0)

        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._duration_ms: int = 0
        self._position_ms: int = 0
        self._was_playing: bool = False   # track state across scrub

        # ── Caption editor ────────────────────────────────────────────────────
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._editor: QLineEdit | None = None
        self._build_caption_editor()

        # ── Restore from session ──────────────────────────────────────────────
        if data.source_path:
            p = Path(data.source_path)
            if p.exists():
                self._set_source(p, restore_pos=data.playback_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION EDITOR  (same pattern as ImageNode)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_caption_editor(self) -> None:
        self._editor = QLineEdit()
        self._editor.setAlignment(Qt.AlignCenter)
        self._editor.setFrame(False)
        self._editor.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.returnPressed.connect(self._commit_caption)
        self._editor.editingFinished.connect(self._commit_caption)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.hide()

    def _caption_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(r.x(), r.bottom() - CAPTION_HEIGHT, r.width(), CAPTION_HEIGHT)

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + VIDEO_PADDING,
            r.bottom() - CAPTION_HEIGHT - PROGRESS_HEIGHT,
            r.width() - VIDEO_PADDING * 2,
            PROGRESS_HEIGHT,
        )

    def _video_rect(self) -> QRectF:
        r = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + VIDEO_PADDING
        return QRectF(
            r.x()     + VIDEO_PADDING,
            top,
            r.width() - VIDEO_PADDING * 2,
            r.height() - (top - r.y()) - VIDEO_PADDING - CAPTION_HEIGHT - PROGRESS_HEIGHT,
        )

    def _start_caption_edit(self) -> None:
        cr = self._caption_rect()
        self._editor_proxy.setGeometry(cr)
        self._editor.setText(self.data.caption)
        self._editor.selectAll()
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
        self._editor_proxy.show()
        self._editor_proxy.setFocus()
        self._editor.setFocus(Qt.MouseFocusReason)

    def _commit_caption(self) -> None:
        if not self._editor_proxy.isVisible():
            return
        self.data.caption = self._editor.text().strip()
        self._editor_proxy.hide()
        self._restore_view_focus()
        self.update()

    def _cancel_caption_edit(self) -> None:
        self._editor_proxy.hide()
        self._restore_view_focus()
        self.update()

    def _restore_view_focus(self) -> None:
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)

    # ─────────────────────────────────────────────────────────────────────────
    # MEDIA PLAYER
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """Load a video from a file path. Public — called by file browser and View.dropEvent."""
        path = Path(path)
        if not path.exists():
            return
        self._set_source(path)
        if not self.data.caption:
            self.data.caption = path.stem
        logger.info(f"video loaded: {path.name}")

    def _set_source(self, path: Path, restore_pos: int = 0) -> None:
        self.data.source_path = str(path.resolve())
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        if restore_pos > 0:
            # Seek after media is loaded — deferred via mediaStatusChanged
            self._restore_pos = restore_pos
        else:
            self._restore_pos = 0

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if hasattr(self, '_restore_pos') and self._restore_pos > 0:
                self._player.setPosition(self._restore_pos)
                self._restore_pos = 0
                # Grab one frame so the node isn't blank
                self._player.play()
                self._player.pause()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.data.looping:
                self._player.setPosition(0)
                self._player.play()

    def _on_frame(self, frame: QVideoFrame) -> None:
        """Convert each video frame to a QPixmap for painting."""
        if not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        self._frame_pixmap = QPixmap.fromImage(img)
        self._scaled_cache = None  # invalidate
        self.update()

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = duration

    def _on_position_changed(self, position: int) -> None:
        self._position_ms = position
        self.update()  # repaint progress bar

    def _toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
        self.update()

    def _toggle_loop(self) -> None:
        self.data.looping = not self.data.looping

    def _stop(self) -> None:
        self._player.stop()
        self.update()

    def _scrub_to(self, x: float) -> None:
        """Seek to position based on x coordinate within the progress bar."""
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        target = int(ratio * self._duration_ms)
        self._player.setPosition(target)

    # ─────────────────────────────────────────────────────────────────────────
    # FILE BROWSER
    # ─────────────────────────────────────────────────────────────────────────

    def _open_file_browser(self) -> None:
        win = self._lower_window()
        start_dir = settings.get_nested("node", "video", "last_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Video",
            start_dir,
            "Videos (*.mp4 *.avi *.mov *.mkv *.webm *.wmv *.flv *.m4v)"
        )
        self._raise_window(win)
        if path:
            settings.set_nested("node", "video", "last_dir", str(Path(path).parent))
            self.load_from_path(path)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        loop_off_pix = Theme.icon(Theme.iconLoopOff, fallback_color="#7a8a9a")
        loop_on_pix  = Theme.icon(Theme.iconLoopOn,  fallback_color="#8cbea0")
        self._loop_btn = NodeButton(self, loop_off_pix, self._toggle_loop, loop_on_pix, toggle=True)
        self._loop_btn._in_confirm = self.data.looping
        self._buttons.append(self._loop_btn)
        trash_pix   = Theme.icon(Theme.iconDelete,  fallback_color="#c97b7b")
        confirm_pix = Theme.icon(Theme.iconConfirm, fallback_color="#d4a96a")
        self._buttons.append(NodeButton(self, trash_pix, self._delete_source_file, confirm_pix))

    def _delete_source_file(self) -> None:
        """Send the source file to the recycle bin, then remove this node."""
        self._player.stop()
        path = self.data.source_path
        if path:
            try:
                from send2trash import send2trash
                send2trash(path)
            except Exception as e:
                logger.warning(f"could not trash '{path}': {e}")
        scene = self.scene()
        if scene:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: scene.removeItem(self))

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        pos = event.pos()
        if self._caption_rect().contains(pos):
            self._start_caption_edit()
            event.accept()
            return
        if self._video_rect().contains(pos):
            if self.data.source_path:
                self._toggle_playback()
            else:
                self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.pos()
        if event.button() == Qt.LeftButton and self._progress_rect().contains(pos):
            self._was_playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if self._was_playing:
                self._player.pause()
            self._scrub_to(pos.x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.pos()
        if self._progress_rect().contains(pos) and event.buttons() & Qt.LeftButton:
            self._scrub_to(pos.x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        pos = event.pos()
        if self._progress_rect().contains(pos) and event.button() == Qt.LeftButton:
            if self._was_playing:
                self._player.play()
                self._was_playing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._editor_proxy and self._editor_proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._cancel_caption_edit()
                event.accept()
                return
            event.accept()
            return
        # Space toggles playback when node is selected
        if event.key() == Qt.Key_Space and self.data.source_path:
            self._toggle_playback()
            event.accept()
            return
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()

        vr = self._video_rect()
        pr = self._progress_rect()
        cr = self._caption_rect()

        if self._frame_pixmap and not self._frame_pixmap.isNull():
            # ── Clip to rounded rect ─────────────────────────────────────────
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(vr, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            # ── Scale + centre ───────────────────────────────────────────────
            vr_size = (int(vr.width()), int(vr.height()))
            if self._scaled_cache is None or self._scaled_cache_size != vr_size:
                self._scaled_cache = self._frame_pixmap.scaled(
                    int(vr.width()), int(vr.height()),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._scaled_cache_size = vr_size
            scaled = self._scaled_cache
            draw_x = vr.x() + (vr.width()  - scaled.width())  / 2.0
            draw_y = vr.y() + (vr.height() - scaled.height()) / 2.0
            painter.drawPixmap(QPointF(draw_x, draw_y), scaled)
            painter.setClipping(False)

            # ── Bevel border ─────────────────────────────────────────────────
            bevel_r = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
            painter.drawRoundedRect(vr, bevel_r, bevel_r)
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            painter.drawRoundedRect(
                vr.adjusted(1, 1, -1, -1),
                max(CLIP_RADIUS_MIN, bevel_r - 1),
                max(CLIP_RADIUS_MIN, bevel_r - 1),
            )
        else:
            # ── Placeholder ──────────────────────────────────────────────────
            painter.setPen(QPen(QColor(Theme.primaryBorder), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(vr, CLIP_RADIUS_MIN, CLIP_RADIUS_MIN)
            painter.setPen(QColor(Theme.healthColorLabel))
            painter.drawText(vr, Qt.AlignCenter, "double-click\nto load video")

        # ── Progress bar ─────────────────────────────────────────────────────
        bar_bg = QColor(Theme.nodeBg).lighter(130)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bar_bg)
        painter.drawRoundedRect(pr, 3, 3)

        if self._duration_ms > 0:
            ratio = self._position_ms / self._duration_ms
            fill_w = pr.width() * ratio
            fill_rect = QRectF(pr.left(), pr.top(), fill_w, pr.height())
            painter.setBrush(QColor(Theme.primaryBorder))
            painter.drawRoundedRect(fill_rect, 3, 3)

            # Time label
            time_text = f"{_fmt_time(self._position_ms)} / {_fmt_time(self._duration_ms)}"
            painter.setPen(QColor(Theme.textPrimary))
            font = painter.font()
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(pr, Qt.AlignCenter, time_text)

        # ── Play state indicator ─────────────────────────────────────────────
        if self.data.source_path and self._frame_pixmap:
            is_playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if not is_playing:
                # Draw a subtle play triangle in the centre of the video area
                cx = vr.center().x()
                cy = vr.center().y()
                tri_size = min(vr.width(), vr.height()) * 0.15
                tri_size = max(12, min(tri_size, 36))
                painter.setBrush(QColor(255, 255, 255, 120))
                painter.setPen(Qt.NoPen)
                path = QPainterPath()
                path.moveTo(cx - tri_size * 0.4, cy - tri_size * 0.5)
                path.lineTo(cx + tri_size * 0.5, cy)
                path.lineTo(cx - tri_size * 0.4, cy + tri_size * 0.5)
                path.closeSubpath()
                painter.drawPath(path)

        # ── Caption band ─────────────────────────────────────────────────────
        if not self._editor_proxy or not self._editor_proxy.isVisible():
            caption_text = self.data.caption or self.data.title
            painter.setPen(QColor(Theme.textPrimary))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(cr, Qt.AlignCenter, caption_text)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._player.stop()
        self._sink.videoFrameChanged.disconnect(self._on_frame)
        self._player.durationChanged.disconnect(self._on_duration_changed)
        self._player.positionChanged.disconnect(self._on_position_changed)
        self._player.mediaStatusChanged.disconnect(self._on_media_status)
        if self._editor_proxy and self._editor_proxy.isVisible():
            self._editor_proxy.hide()
            self._restore_view_focus()
        self._frame_pixmap = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.data.playback_pos = self._position_ms
        self.data.volume = int(self._audio.volume() * 100)
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'VideoNode':
        return VideoNode(VideoNodeData.from_dict(data))
