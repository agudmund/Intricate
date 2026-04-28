#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/VideoNode.py VideoNode class
-the picture moves on its own now, sized to the room as the room changes
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
from pathlib import Path

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QPainterPath, QLinearGradient
)

from nodes.BaseNode import BaseNode
from data.VideoNodeData import VideoNodeData, LOOP_MODES
from utils.video_decoder import VideoDecoder
from pretty_widgets.graphics.Theme import Theme
import pretty_widgets.utils.settings as settings
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("video")


# Layout constants
PROGRESS_HEIGHT  = 14.0     # Height of the scrub/progress bar
VIDEO_PADDING    = 6.0      # Inset on all sides
CLIP_RADIUS_MIN  = 2.0      # Minimum clip radius inside the padding

_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv", ".m4v"}
_BUTTON_ZONE_H    = 40.0   # px reserved for button strip (4 pad + 32 button + 4 gap)


def _fmt_time(ms: int) -> str:
    """Format milliseconds as m:ss."""
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class VideoNode(BaseNode):
    """
    Renders video with frame-accurate playback inside the node body.

    Backend: PyAV (ffmpeg Python bindings) via utils.video_decoder.VideoDecoder.
    See Documents/Design/A-V Transport Engine — Forward Design Exploration.md
    for the staging plan this slots into. This is Stage 3 of that plan landed
    standalone — the Transport seat (Stage 2) and the AudioNode swap (Stage 4)
    arrive in their own passes. VideoNode no longer carries audio at all
    (Stage 1 amputation): audio is AudioNode's exclusive domain in the
    Transport architecture.

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

    Interaction zones:
        Caption band  → activate inline QLineEdit editor (BaseNode handles)
        Video area    → open file browser (when empty) or toggle play/pause
        Progress bar  → scrub to position

    OS drag and drop:
        Handled by IntricateView.dropEvent — video files dragged from Explorer
        land on the view, get mapped to scene coordinates, and a VideoNode
        receives the path via load_from_path().
    """

    _show_ports_btn = False   # ports toggle hidden — re-enable for debug
    _has_depth_toggle = True
    _resize_grip = 64         # bigger grip — VideoNode is often resized,
                              # and the rest of the node is a busy click
                              # target (frame, progress, buttons), so the
                              # grip earns its space in the corner.
    _resize_overreach = 0     # No outward flap — the BR port lives just
                              # past the corner at (right+10, bottom+10)
                              # with an 8px hit radius. Keeping the resize
                              # zone strictly inside the rect avoids any
                              # spatial overlap with the port when wiring
                              # mode shows the ports. The 64px grip is
                              # plenty grabbable without the overreach.
    _user_paused = False      # set False at class level so _build_buttons
                              # (called from BaseNode.__init__) can read it
                              # before the per-instance assignment

    def __init__(self, data: VideoNodeData | None = None):
        if data is None:
            data = VideoNodeData()
        super().__init__(data)

        self._destroyed = False   # set by _prepare_for_removal to guard signal callbacks
        self._spawn_label = True  # set False to suppress caption AboutNode on load
        self._aspect_fitted = False  # True once we've auto-sized to the video's aspect ratio

        # ── Current frame pixmap ──────────────────────────────────────────────
        # The decoder sizes each frame at decode time to the LOD-bounded
        # target — so the pixmap that lands here is already screen-resolution.
        # Paint draws it aspect-fit and centred in the video rect.
        self._frame_pixmap: QPixmap | None = None
        self._scaled_cache: QPixmap | None = None
        self._scaled_cache_size: tuple[int, int] | None = None
        self._last_lod: float = 1.0

        # ── PyAV decoder ──────────────────────────────────────────────────────
        # One decoder per node, single worker thread, signal-based delivery
        # back to the main GUI thread. See utils/video_decoder.py.
        self._decoder = VideoDecoder()
        self._decoder.signals.frame.connect(self._on_decoder_frame)
        self._decoder.signals.position.connect(self._on_decoder_position)
        self._decoder.signals.duration.connect(self._on_decoder_duration)
        self._decoder.signals.state.connect(self._on_decoder_state)
        self._decoder.signals.error.connect(self._on_decoder_error)

        self._duration_ms: int = 0
        self._position_ms: int = 0
        self._scrubbing: bool = False        # progress bar drag in progress
        self._was_playing: bool = False      # remember play state across scrub

        self._viewport_visible: bool = True  # assume visible until told otherwise
        self._was_playing_before_cull: bool = False

        # Button row starts hidden — double-click the top strip to reveal
        self._buttons_visible = False
        self._anim_top_offset = 8.0
        for btn in self._buttons:
            btn.hide()

        # Background cache/drift delivery flags — polled by main-thread timer.
        # Same pattern as ImageNode's _pending_pixmap / _pending_cache_key.
        self._pending_cache_key: str | None = None
        self._pending_drift:     str | None = None
        self._pending_size:      int  | None = None
        self._pending_mtime:     float | None = None
        self._cache_poll = QTimer()
        self._cache_poll.setInterval(100)
        self._cache_poll.timeout.connect(self._check_cache_delivery)
        self._cache_poll.start()

        # ── Restore from session ──────────────────────────────────────────────
        # Permanence contract: prefer live source (drift-checked async); fall
        # back to cached copy; placeholder if both gone. Drift AboutNode on
        # mismatch — surface the signal, never auto-heal.
        self._restore_from_session()

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _top_offset(self) -> float:
        """Vertical space reserved above the video — full button zone or minimal pad."""
        return _BUTTON_ZONE_H if self._buttons_visible else 15.0

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + VIDEO_PADDING,
            r.bottom() - PROGRESS_HEIGHT - VIDEO_PADDING,
            r.width() - VIDEO_PADDING * 2,
            PROGRESS_HEIGHT,
        )

    def _video_rect(self) -> QRectF:
        r = self.rect()
        top = r.y() + self._top_offset() + VIDEO_PADDING
        bottom_reserve = (PROGRESS_HEIGHT + VIDEO_PADDING) if self._buttons_visible else 0.0
        return QRectF(
            r.x()     + VIDEO_PADDING,
            top,
            r.width() - VIDEO_PADDING * 2,
            r.height() - (top - r.y()) - VIDEO_PADDING - bottom_reserve,
        )

    def _spawn_caption_node(self, caption: str) -> None:
        """Spawn an AboutNode with *caption* and wire it to this VideoNode."""
        scene = self.scene()
        if not scene:
            return
        pos = self.scenePos()
        about_pos = QPointF(pos.x(), pos.y() + self.rect().height() + 20)
        about = scene.add_about_node(pos=about_pos, label=caption)

        from graphics.Connection import Connection
        conn = Connection(self, about)
        scene.addItem(conn)
        conn.update_path()

    # ─────────────────────────────────────────────────────────────────────────
    # SOURCE / DECODER WIRING
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """Load a video from a file path. Public — called by file browser and View.dropEvent.

        First touch on a node: open the file, decode the first frame so the
        node has something to show, then sit paused. The user starts playback
        explicitly. (Session restore is the *other* entry point and follows
        the saved was_playing intent — see `_restore_from_session`.)
        """
        path = Path(path)
        if not path.exists():
            return
        self._set_source(path, start_paused=True)
        if not self.data.caption and self._spawn_label:
            self.data.caption = path.stem
            self._spawn_caption_node(path.stem)
        logger.info(f"video loaded: {path.name}")
        # Fire-and-forget cache ingestion. See _check_cache_delivery for pickup.
        self._start_cache_ingest(path)

    def _set_source(self, path: Path, restore_pos: int = 0,
                    start_paused: bool = True) -> None:
        """Tell the decoder to open `path`. The initial LOD size is a sensible
        guess derived from the current video rect; the decoder honours
        set_lod_size() updates as the view zooms in/out.

        `start_paused` defaults to True — initial drag/browse loads should
        not autoplay. Session restore overrides this based on the saved
        was_playing flag.
        """
        self.data.source_path = str(path.resolve())
        target_w, target_h = self._target_lod_size()
        self._user_paused = bool(start_paused)
        self._decoder.set_source(
            path,
            lod_size=(target_w, target_h),
            loop_mode=self.data.loop_mode,
            start_paused=self._user_paused,
            start_position_ms=int(restore_pos) if restore_pos > 0 else 0,
        )
        # Keep the play sticker in sync with the actual starting state.
        btn = getattr(self, "_play_btn", None)
        if btn is not None:
            btn._in_confirm = not self._user_paused
            btn.update()

    def _target_lod_size(self) -> tuple[int, int]:
        """Compute (target_w, target_h) for decoder LOD sizing — video_rect
        × current view zoom. Used at load time and on every viewport change.
        Falls back to a 1.0× sizing when no view has attached yet."""
        try:
            vr = self._video_rect()
            lod = self._current_view_lod()
            return max(1, int(vr.width() * lod) + 1), max(1, int(vr.height() * lod) + 1)
        except RuntimeError:
            return 320, 240

    def _current_view_lod(self) -> float:
        """Return the current view's zoom factor (quantized to 0.5 steps).
        One-view assumption matches the app today; falls back to 1.0 if
        the scene has not yet attached a view (early session restore)."""
        try:
            sc = self.scene()
            views = sc.views() if sc else []
            if not views:
                return 1.0
            raw = max(1.0, abs(views[0].transform().m11()))
        except RuntimeError:
            return 1.0
        return max(1.0, math.ceil(raw * 2.0) / 2.0)

    def _restore_from_session(self) -> None:
        """Session restore with permanence contract.

        Preference order:
            1. Source file on disk exists → play from source, drift-check async
            2. Cache key resolves         → play from cache, flag source missing
            3. Neither                    → placeholder, node remains empty

        Restore honours `data.was_playing` — clips that were rolling when
        the session was saved resume rolling, clips that were paused stay
        paused. (Initial drag/browse loads always start paused; that's
        `load_from_path`'s contract, distinct from this one.)
        """
        from utils.persistence.media_cache import cached_path

        src_path = Path(self.data.source_path) if self.data.source_path else None
        cache_path = cached_path(self.data.cache_key) if self.data.cache_key else None
        start_paused = not bool(self.data.was_playing)

        if src_path and src_path.exists():
            self._set_source(src_path, restore_pos=self.data.playback_pos,
                             start_paused=start_paused)
            if self.data.cache_key:
                self._start_drift_check(src_path)
            else:
                # Pre-cache session: ingest now so future restores are safe.
                self._start_cache_ingest(src_path)
            return

        if cache_path is not None:
            self._set_source(cache_path, restore_pos=self.data.playback_pos,
                             start_paused=start_paused)
            missing = self.data.source_path or "(unknown)"
            self._pending_drift = f"source missing — playing from cache\n{Path(missing).name}"
            return

        # Nothing to load — empty placeholder node.

    # ─────────────────────────────────────────────────────────────────────────
    # CACHE — background ingestion and drift detection (preserved from
    # pre-PyAV; the cache contract is backend-agnostic, only the playback
    # path changed)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_cache_ingest(self, src_path: Path) -> None:
        """Hash + copy the source into the media cache on a daemon thread."""
        import threading
        def _worker(node=self, path=src_path):
            try:
                from utils.persistence.media_cache import cache_source_file
                key = cache_source_file(path)
                if not key:
                    return
                try:
                    st = path.stat()
                    size, mtime = st.st_size, st.st_mtime
                except OSError:
                    size, mtime = 0, 0.0
                node._pending_size  = size
                node._pending_mtime = mtime
                node._pending_cache_key = key
            except Exception as e:
                logger.warning(f"[video cache] ingest failed for {path.name}: {e}")
        threading.Thread(target=_worker, daemon=True, name="video-cache-ingest").start()

    def _start_drift_check(self, src_path: Path) -> None:
        """Cheap fingerprint (size + mtime) against the stored values. Only
        if either has changed do we spend a full re-hash to confirm a real
        content change. Surface the signal via _pending_drift; never auto-heal."""
        import threading
        def _worker(node=self, path=src_path):
            try:
                try:
                    st = path.stat()
                except OSError:
                    return
                if (st.st_size == node.data.source_size
                        and abs(st.st_mtime - node.data.source_mtime) < 1.0):
                    return
                from utils.persistence.media_cache import hash_file, key_hash
                live_hash = hash_file(path)
                if live_hash is None:
                    return
                if live_hash != key_hash(node.data.cache_key):
                    node._pending_drift = (
                        "source drifted — cache no longer matches\n"
                        f"{path.name}"
                    )
            except Exception as e:
                logger.warning(f"[video cache] drift check failed for {path.name}: {e}")
        threading.Thread(target=_worker, daemon=True, name="video-cache-drift").start()

    def _check_cache_delivery(self) -> None:
        """Main-thread pickup of background cache / drift workers."""
        if not self._timer_slot_alive('_cache_poll'):
            return
        if self._destroyed:
            return

        key = self._pending_cache_key
        if key:
            self.data.cache_key = key
            if self._pending_size  is not None:
                self.data.source_size  = self._pending_size
            if self._pending_mtime is not None:
                self.data.source_mtime = self._pending_mtime
            self._pending_cache_key = None
            self._pending_size  = None
            self._pending_mtime = None

        drift_msg = self._pending_drift
        if drift_msg:
            self._pending_drift = None
            try:
                self._spawn_caption_node(drift_msg)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # DECODER SLOTS (signals fire on the worker thread; Qt queues them onto
    # the main thread, so these run with the GUI lock)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_decoder_frame(self, qimg: QImage) -> None:
        """Receive a decoded frame from the worker thread. The image is
        already sized to LOD (decoder honours set_lod_size). Convert to
        QPixmap and trigger a repaint."""
        if self._destroyed or qimg.isNull():
            return

        # Auto-fit node width to the source video's aspect ratio on first
        # frame received. Subsequent frames keep the fit.
        if not self._aspect_fitted and qimg.width() > 0 and qimg.height() > 0:
            self._aspect_fitted = True
            vid_aspect = qimg.width() / qimg.height()
            r = self.rect()
            vr = self._video_rect()
            ideal_vr_w = vr.height() * vid_aspect
            h_pad = r.width() - vr.width()
            ideal_node_w = ideal_vr_w + h_pad
            if abs(ideal_node_w - r.width()) > 2.0:
                self.prepareGeometryChange()
                self.setRect(QRectF(r.x(), r.y(), ideal_node_w, r.height()))
                self.data.width = ideal_node_w

        self._frame_pixmap = QPixmap.fromImage(qimg)
        self._scaled_cache = None       # invalidate aspect-fit cache
        self.update()

    def _on_decoder_position(self, ms: int) -> None:
        if self._destroyed:
            return
        self._position_ms = ms

    def _on_decoder_duration(self, ms: int) -> None:
        if self._destroyed:
            return
        self._duration_ms = ms

    def _on_decoder_state(self, state: str) -> None:
        # Reserved for future hooks — e.g. surfacing a "ended" overlay when
        # loop_mode == "off" and the clip finishes. No-op for now.
        pass

    def _on_decoder_error(self, msg: str) -> None:
        logger.warning("decoder error on %s: %s", self.data.source_path, msg)

    # ─────────────────────────────────────────────────────────────────────────
    # PLAYBACK CONTROL
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_playback(self) -> None:
        # NodeButton has already flipped _in_confirm before invoking us:
        #   _in_confirm True  → pause icon shown → user wants playback.
        #   _in_confirm False → play  icon shown → user wants paused.
        # Single source of truth; no recomputation.
        want_play = bool(self._play_btn._in_confirm)
        self._user_paused = not want_play
        if want_play:
            if self._viewport_visible:
                self._decoder.play()
        else:
            self._decoder.pause()
        self.update()

    def _cycle_loop_mode(self) -> None:
        """Cycle off → loop → pingpong → off → ..."""
        try:
            idx = LOOP_MODES.index(self.data.loop_mode)
        except ValueError:
            idx = 0
        self.data.loop_mode = LOOP_MODES[(idx + 1) % len(LOOP_MODES)]
        self._decoder.set_loop_mode(self.data.loop_mode)
        # Refresh button visual + tooltip
        self._refresh_loop_button_visual()
        self.update()

    def _refresh_loop_button_visual(self) -> None:
        """Sync the loop button's pixmap and tooltip to data.loop_mode."""
        btn = getattr(self, "_loop_btn", None)
        if btn is None:
            return
        mode = self.data.loop_mode
        # The three icons are stored on the button itself at construction.
        pix = self._loop_pix_off
        if   mode == "loop":     pix = self._loop_pix_loop
        elif mode == "pingpong": pix = self._loop_pix_pingpong
        # NodeButton renders from `_pix` (set by the constructor as the
        # "main" pixmap). Reassigning it and triggering update() is enough.
        btn._pix = pix
        btn._in_confirm = False  # we manage state ourselves; stay on main face
        btn.setToolTip(f"Loop: {mode}")
        btn.update()

    def _scrub_to(self, x: float) -> None:
        """Seek the decoder to the position represented by *x* on the
        progress bar. The decoder picks up the seek on its next iteration."""
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        target = int(ratio * self._duration_ms)
        self._decoder.set_position(target)

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
        from nodes.NodeButton import NodeButton, EmojiButton
        super()._build_buttons()

        # Play/pause — sticker toggle. NodeButton flips _in_confirm itself
        # on click; _toggle_playback reads it as the source of truth.
        play_pix  = Theme.icon(Theme.iconPlayIconic,  fallback_color="#9a7abf")
        pause_pix = Theme.icon(Theme.iconPauseIconic, fallback_color="#9a7abf")
        self._play_btn = NodeButton(
            self, play_pix, self._toggle_playback,
            pixmap_confirm=pause_pix, toggle=True,
        )
        self._play_btn._sticker_shadow = True
        self._play_btn._in_confirm = not self._user_paused
        self._play_btn.setToolTip("Play / Pause")
        self._buttons.append(self._play_btn)

        # Loop — three states cycled by a single button. NodeButton's
        # built-in toggle is binary, so we run in single-stage mode and
        # swap the displayed pixmap manually in _refresh_loop_button_visual.
        self._loop_pix_off      = Theme.icon(Theme.iconReturnIconic,  fallback_color="#9a7abf")
        self._loop_pix_loop     = Theme.icon(Theme.iconLoopAudio,     fallback_color="#9a7abf")
        self._loop_pix_pingpong = Theme.icon(Theme.iconPingpong,      fallback_color="#9a7abf")
        self._loop_btn = NodeButton(
            self, self._loop_pix_off, self._cycle_loop_mode,
        )
        self._loop_btn._sticker_shadow = True
        self._buttons.append(self._loop_btn)
        # Sync icon to current mode (handles session restore).
        self._refresh_loop_button_visual()

        # Border toggle — simple circle, state is visible on the node itself
        self._border_btn = EmojiButton(
            self,
            get_emoji=lambda: "○",  # ○
            set_emoji=lambda _: self._toggle_border(),
        )
        self._border_btn.setToolTip("Toggle ivory border")
        self._buttons.append(self._border_btn)

    def _toggle_border(self) -> None:
        self.data.show_border = not self.data.show_border
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        # Top strip above the video area — animated shelf toggle
        if event.pos().y() < self.rect().top() + self._top_offset():
            self._toggle_shelf()
            event.accept()
            return
        if self._video_rect().contains(event.pos()):
            if self.data.source_path:
                # Double-click on video toggles playback by mirroring a
                # play-button click — keep _in_confirm in sync with the
                # intended new state, then dispatch.
                if hasattr(self, "_play_btn"):
                    self._play_btn._in_confirm = self._user_paused  # flip
                self._toggle_playback()
            else:
                self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.pos()
        if self._buttons_visible and event.button() == Qt.LeftButton:
            # The resize handle lives in the bottom-right corner, which the
            # progress bar's full-width span also covers. Skip our own
            # interaction handling inside the resize zone so super() (i.e.
            # BaseNode) gets the click and starts a resize. Without this,
            # the progress scrub eats every corner click and resize is dead.
            rect = self.rect()
            grip = self._resize_grip
            in_resize_zone = (
                pos.x() >= rect.right()  - grip
                and pos.y() >= rect.bottom() - grip
            )
            if not in_resize_zone and self._progress_rect().contains(pos):
                self._scrubbing = True
                self._was_playing = not self._user_paused
                if self._was_playing:
                    self._decoder.pause()
                self._scrub_to(pos.x())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._scrubbing and event.buttons() & Qt.LeftButton:
            self._scrub_to(event.pos().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._scrubbing and event.button() == Qt.LeftButton:
            self._scrubbing = False
            if self._was_playing and self._viewport_visible:
                self._decoder.play()
                self._was_playing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        # Space toggles playback when node is selected
        if event.key() == Qt.Key_Space and self.data.source_path:
            if hasattr(self, "_play_btn"):
                self._play_btn._in_confirm = self._user_paused
            self._toggle_playback()
            event.accept()
            return
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """
        LOD-aware content tier. The decoder sizes each frame at decode time,
        so paint just aspect-fits the current pixmap into the video rect
        and draws. Zoom changes propagate to the decoder via set_lod_size().
        """
        painter.save()

        vr = self._video_rect()
        pr = self._progress_rect()

        # ── LOD update — push to decoder if the view zoom moved past a step
        try:
            raw_lod = max(1.0, abs(painter.worldTransform().m11()))
            cur_lod = max(1.0, math.ceil(raw_lod * 2.0) / 2.0)
            if cur_lod != self._last_lod:
                self._last_lod = cur_lod
                tw = max(1, int(vr.width()  * cur_lod) + 1)
                th = max(1, int(vr.height() * cur_lod) + 1)
                self._decoder.set_lod_size(tw, th)
        except RuntimeError:
            pass

        if self._frame_pixmap and not self._frame_pixmap.isNull():
            # Clip to rounded rect
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(vr, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
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

            # Border
            bevel_r = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            painter.setBrush(Qt.NoBrush)
            if self.data.show_border:
                painter.setPen(QPen(QColor(225, 213, 198, 255), 3))
                painter.drawRoundedRect(
                    vr.adjusted(1, 1, -1, -1), bevel_r, bevel_r,
                )
            else:
                painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
                painter.drawRoundedRect(vr, bevel_r, bevel_r)
                painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
                painter.drawRoundedRect(
                    vr.adjusted(1, 1, -1, -1),
                    max(CLIP_RADIUS_MIN, bevel_r - 1),
                    max(CLIP_RADIUS_MIN, bevel_r - 1),
                )
        else:
            # Placeholder
            painter.setPen(QPen(QColor(Theme.primaryBorder), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(vr, CLIP_RADIUS_MIN, CLIP_RADIUS_MIN)
            painter.setPen(QColor(Theme.healthColorLabel))
            painter.drawText(vr, Qt.AlignCenter, "double-click\nto load video")

        # Progress bar (only when button row is visible)
        if self._buttons_visible:
            bar_bg = QColor(Theme.nodeBg).lighter(130)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bar_bg)
            painter.drawRoundedRect(pr, 3, 3)

            if self._duration_ms > 0:
                ratio = self._position_ms / self._duration_ms
                fill_w = pr.width() * ratio
                fill_rect = QRectF(pr.left(), pr.top(), fill_w, pr.height())
                grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
                grad.setColorAt(0.0, QColor("#1e1e1e"))
                grad.setColorAt(0.4, QColor("#5c3e4f"))
                grad.setColorAt(0.7, QColor("#a56a85"))
                grad.setColorAt(1.0, QColor("#d87a9e"))
                painter.setBrush(grad)
                painter.drawRoundedRect(fill_rect, 3, 3)

        # Centre play-state indicator — visible whenever paused on a loaded clip
        if self.data.source_path and self._frame_pixmap and self._user_paused:
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

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # VIEWPORT CULLING
    # ─────────────────────────────────────────────────────────────────────────

    def _set_viewport_visible(self, visible: bool) -> None:
        """Pause when the node leaves the viewport, resume when it returns.
        With audio gone there's no fade to manage — the cull/uncull pair is
        a clean play/pause swap on the decoder."""
        if visible == self._viewport_visible:
            return
        self._viewport_visible = visible
        if not self.data.source_path:
            return
        if visible:
            if self._was_playing_before_cull and not self._user_paused:
                self._decoder.play()
                self._was_playing_before_cull = False
        else:
            if not self._user_paused:
                # Track that the user wanted playback so we resume on uncull
                self._was_playing_before_cull = True
                self._decoder.pause()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE / TEARDOWN
    # ─────────────────────────────────────────────────────────────────────────

    def _quiet_for_shake(self) -> None:
        """Sever the media pipeline synchronously at shake-trigger time.

        Carried over from the QMediaPlayer era: shake-delete leaves an
        8000-sprite particle window during which the decoder would keep
        running. With PyAV the consequences are gentler — there is no
        WMF heap to corrupt — but we still want clean shutdown and a
        responsive shake animation. close() blocks decoder signals and
        joins the worker thread (bounded), so any late frame events that
        sneak through are dropped harmlessly.
        """
        try:
            self._decoder.signals.frame.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            self._decoder.close()
        except Exception:
            pass

    # Crew sets _destroyed FIRST so background ingest/drift workers
    # bail before any teardown writes to dead state.
    _demolition_thread_flag = '_destroyed'
    _demolition_timers = [('_cache_poll', '_check_cache_delivery')]

    def _demolition_pre(self) -> None:
        # Null pending fields — the background thread has already bailed
        # via the _destroyed flag that the crew set; anything still
        # in-flight is safe to drop.
        self._pending_cache_key = None
        self._pending_drift     = None
        self._pending_size      = None
        self._pending_mtime     = None

        # Disconnect every decoder signal — Qt's queued connections
        # could otherwise deliver to a half-demolished node after the
        # worker thread emits one last frame.
        for sig_name in ("frame", "position", "duration", "state", "error"):
            try:
                getattr(self._decoder.signals, sig_name).disconnect()
            except (RuntimeError, TypeError, AttributeError):
                pass

        # Stop the worker thread (joined inside close()) and release the
        # av.container. Idempotent — _quiet_for_shake may have called this
        # already on the shake path.
        try:
            self._decoder.close()
        except Exception:
            pass

    def _demolition_post(self) -> None:
        self._frame_pixmap = None
        self._scaled_cache = None
        # Drop the decoder reference so any stale slot calls hit
        # AttributeError rather than the dead QObject behind it.
        self._decoder = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        # Every read here uses getattr-with-default so to_dict can never
        # raise, even on a partially-initialised or partially-demolished
        # node. See [to_dict never raises contract] in project memory.
        pos_ms = getattr(self, '_position_ms', None)
        if pos_ms is not None:
            self.data.playback_pos = int(pos_ms)
        dec = getattr(self, '_decoder', None)
        if dec is not None:
            try:
                # was_playing := the user's intent (not a transient cull).
                self.data.was_playing = (
                    not dec.is_paused()
                    or getattr(self, '_was_playing_before_cull', False)
                )
            except (RuntimeError, AttributeError):
                pass
        try:
            self.sync_data()
        except Exception:
            pass
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'VideoNode':
        return VideoNode(VideoNodeData.from_dict(data))
