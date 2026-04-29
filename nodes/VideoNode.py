#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/VideoNode.py VideoNode class
-Renders video with full playback inside the canvas via QMediaPlayer for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
from pathlib import Path

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt, QRectF, QPointF, QUrl, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QPainterPath, QLinearGradient
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame

from nodes.BaseNode import BaseNode
from data.VideoNodeData import VideoNodeData
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

    _show_ports_btn = False   # ports toggle hidden — re-enable for debug
    _has_depth_toggle = True
    # Resize zone is a 128×128 square centered exactly on the bottom-right
    # corner — 64 px inward into the body and 64 px outward past the rect.
    # The symmetry is the point: when working fast, the cursor lands
    # "approximately at the corner" with high tolerance in either direction,
    # and either side of the literal corner edge feels equally responsive.
    _resize_grip = 64
    _resize_overreach = 64

    def __init__(self, data: VideoNodeData | None = None):
        if data is None:
            data = VideoNodeData()
        super().__init__(data)

        self._destroyed = False   # set by _prepare_for_removal to guard signal callbacks
        self._spawn_label = True  # set False to suppress caption AboutNode on load
        self._aspect_fitted = False  # True once we've auto-sized to the video's aspect ratio

        # ── Current frame pixmap ──────────────────────────────────────────────
        # Frame pixmap is sized at ingest to match the current view LOD so we
        # never upscale a proxy-sized bitmap at extreme zoom (pixelation) nor
        # keep a full source-resolution frame per video (memory blow-up when
        # hundreds of clips play simultaneously in an animatic view).
        self._frame_pixmap: QPixmap | None = None
        self._scaled_cache: QPixmap | None = None
        self._scaled_cache_size: tuple[int, int] | None = None
        self._frame_pending: bool = False          # throttle: skip if paint hasn't caught up
        self._last_lod: float = 1.0                # quantized LOD the current frame was sized for

        # ── Media player ──────────────────────────────────────────────────────
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._sink   = QVideoSink()

        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._sink)
        self._audio.setVolume(data.volume / 100.0)
        from utils.audio import audio as _audio_mgr
        self._audio.setMuted(data.muted or _audio_mgr.is_muted())

        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._duration_ms: int = 0
        self._position_ms: int = 0
        self._was_playing: bool = False   # track state across scrub
        self._scrubbing: bool = False     # progress bar drag in progress
        self._volume_scrubbing: bool = False  # volume slider drag in progress

        self._viewport_visible: bool = True   # assume visible until told otherwise
        self._was_playing_before_cull: bool = False
        self._volume_anim: QPropertyAnimation | None = None
        self._target_volume: float = data.volume / 100.0  # user's intended volume

        # Button row starts hidden. Reveal is bound to the resize gesture
        # (mirrors AboutNode): drag the bottom-right corner downward past
        # the reveal threshold to surface the shelf, drag back upward past
        # the hide threshold to tuck it away. The top strip's previous
        # double-click toggle is gone — see _RESIZE_SHELF_*_THRESHOLD and
        # mouseMoveEvent below.
        self._buttons_visible = False
        self._anim_top_offset = 8.0
        for btn in self._buttons:
            btn.hide()
        self._shelf_anchor_h: float | None = None

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
        # Permanence contract: the graph remembers every video it has ever
        # been given. Prefer the live source (drift-checked in background);
        # fall back to the cached copy if the source has moved, been lost,
        # or is mid-network-mount. A drift AboutNode is spawned on mismatch —
        # we surface the signal, never auto-heal.
        self._restore_from_session()

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION → ABOUT NODE
    # ─────────────────────────────────────────────────────────────────────────

    def _top_offset(self) -> float:
        """Vertical space reserved above the video — full button zone or minimal pad."""
        return _BUTTON_ZONE_H if self._buttons_visible else 15.0

    def _progress_rect(self) -> QRectF:
        # Progress bar ends short of the resize zone so a quick resize-grab
        # doesn't snag the scrub. Mirrors AudioNode's "right-side breathing
        # room" pattern. The end-of-bar marker is painted at this right
        # edge in paint_content so the truncation is legible to the user.
        r = self.rect()
        vol_reserve = PROGRESS_HEIGHT + VIDEO_PADDING if self._buttons_visible else 0.0
        right_margin = self._resize_grip + VIDEO_PADDING
        return QRectF(
            r.x() + VIDEO_PADDING + vol_reserve,
            r.bottom() - PROGRESS_HEIGHT - VIDEO_PADDING,
            r.width() - VIDEO_PADDING - right_margin - vol_reserve,
            PROGRESS_HEIGHT,
        )

    def _volume_rect(self) -> QRectF:
        """Vertical volume slider — left edge of the video area, same width as
        the progress bar height so they feel like siblings."""
        vr = self._video_rect()
        return QRectF(
            self.rect().x() + VIDEO_PADDING,
            vr.y(),
            PROGRESS_HEIGHT,
            vr.height() + PROGRESS_HEIGHT + VIDEO_PADDING,
        )

    def _video_rect(self) -> QRectF:
        r = self.rect()
        top = r.y() + self._top_offset() + VIDEO_PADDING
        bottom_reserve = (PROGRESS_HEIGHT + VIDEO_PADDING) if self._buttons_visible else 0.0
        vol_reserve = (PROGRESS_HEIGHT + VIDEO_PADDING) if self._buttons_visible else 0.0
        return QRectF(
            r.x()     + VIDEO_PADDING + vol_reserve,
            top,
            r.width() - VIDEO_PADDING * 2 - vol_reserve,
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
    # MEDIA PLAYER
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """Load a video from a file path. Public — called by file browser and View.dropEvent.

        Playback starts immediately from the source path so the user never waits
        on the cache. A background worker hashes + copies the source bytes
        into the media cache and stamps data.cache_key on completion. From
        that moment on the graph knows about the video and can restore it
        even if the source file later moves or disappears.
        """
        path = Path(path)
        if not path.exists():
            return
        self._set_source(path)
        if not self.data.caption and self._spawn_label:
            self.data.caption = path.stem
            self._spawn_caption_node(path.stem)
        logger.info(f"video loaded: {path.name}")
        # Fire-and-forget cache ingestion. See _check_cache_delivery for pickup.
        self._start_cache_ingest(path)

    def _set_source(self, path: Path, restore_pos: int = 0) -> None:
        self.data.source_path = str(path.resolve())
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        if restore_pos > 0:
            # Seek after media is loaded — deferred via mediaStatusChanged
            self._restore_pos = restore_pos
        else:
            self._restore_pos = 0

    def _restore_from_session(self) -> None:
        """Session restore with permanence contract.

        Preference order:
            1. Source file on disk exists → play from source, drift-check async
            2. Cache key resolves         → play from cache, flag source missing
            3. Neither                    → placeholder, node remains empty
        """
        from utils.persistence.media_cache import cached_path

        src_path = Path(self.data.source_path) if self.data.source_path else None
        cache_path = cached_path(self.data.cache_key) if self.data.cache_key else None

        if src_path and src_path.exists():
            self._set_source(src_path, restore_pos=self.data.playback_pos)
            if self.data.cache_key:
                # Drift check is deferred to a background worker — cheap
                # fingerprint (size + mtime) first, full rehash only on mismatch.
                self._start_drift_check(src_path)
            else:
                # Pre-cache session: ingest now so future restores are safe.
                self._start_cache_ingest(src_path)
            return

        if cache_path is not None:
            self._set_source(cache_path, restore_pos=self.data.playback_pos)
            # Flag that the live source is gone — the graph self-served from cache.
            missing = self.data.source_path or "(unknown)"
            self._pending_drift = f"source missing — playing from cache\n{Path(missing).name}"
            return

        # Nothing to load — empty placeholder node.

    # ─────────────────────────────────────────────────────────────────────────
    # CACHE — background ingestion and drift detection
    # ─────────────────────────────────────────────────────────────────────────

    def _start_cache_ingest(self, src_path: Path) -> None:
        """Hash + copy the source into the media cache on a daemon thread.
        Delivers cache_key / size / mtime via _pending_* fields. Safe to call
        multiple times — cache_source_file short-circuits if the hash exists."""
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
                # Write pending fields last — delivery timer treats the key
                # as the "ready" signal.
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
                    return   # clean — no change since last bind
                # Fingerprint mismatch — spend the full hash to confirm drift.
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
        # Orphan-timer guard (see BaseNode._timer_slot_alive) — supersedes
        # the narrower _destroyed probe that previously lived here.
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

    def _on_media_status(self, status) -> None:
        try:
            if self._destroyed:
                return
        except RuntimeError:
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if hasattr(self, '_restore_pos') and self._restore_pos > 0:
                self._player.setPosition(self._restore_pos)
                self._restore_pos = 0
            # Always autoplay on load
            self._player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.data.looping:
                self._player.setPosition(0)
                if self._viewport_visible:
                    self._player.play()
                else:
                    self._was_playing_before_cull = True

    def _current_view_lod(self) -> float:
        """Return the current view's zoom factor (quantized to 0.5 steps).

        Ingest-time LOD lookup — paint sees it through the painter's world
        transform, but _on_frame has no painter so we read it from the view.
        One-view assumption matches the app today; falls back to 1.0 if the
        scene has not yet attached a view (early session restore)."""
        try:
            sc = self.scene()
            views = sc.views() if sc else []
            if not views:
                return 1.0
            raw = max(1.0, abs(views[0].transform().m11()))
        except RuntimeError:
            return 1.0
        return max(1.0, math.ceil(raw * 2.0) / 2.0)

    def _on_frame(self, frame: QVideoFrame) -> None:
        """Convert each video frame to a LOD-sized QPixmap for painting.

        The incoming frame is scaled at ingest to (video_rect × current LOD),
        capped at source resolution. This keeps memory proportional to the
        on-screen size per node — hundreds of tiny clips in an animatic view
        cost little; one zoomed-in clip gets up to source-res for that one
        alone. When zoom changes, playing videos pick up the new LOD on the
        next arrival (16–33ms); paused videos are re-emitted from paint().

        Frame-skip: if the previous frame hasn't been painted yet we drop
        this one entirely (_frame_pending throttle).
        """
        try:
            if self._destroyed or self._frame_pending:
                return
        except RuntimeError:
            return
        if not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return

        # Auto-fit node width to video aspect ratio on first frame
        if not self._aspect_fitted and img.width() > 0 and img.height() > 0:
            self._aspect_fitted = True
            vid_aspect = img.width() / img.height()
            r = self.rect()
            vr = self._video_rect()
            # Derive the ideal video-rect width from current video-rect height
            ideal_vr_w = vr.height() * vid_aspect
            # Add back horizontal padding to get the node width
            h_pad = r.width() - vr.width()
            ideal_node_w = ideal_vr_w + h_pad
            if abs(ideal_node_w - r.width()) > 2.0:
                self.prepareGeometryChange()
                self.setRect(QRectF(r.x(), r.y(), ideal_node_w, r.height()))
                self.data.width = ideal_node_w

        # Size the frame pixmap to (video_rect × LOD), capped at source
        try:
            vr = self._video_rect()
        except RuntimeError:
            return
        lod = self._current_view_lod()
        tw = max(1, min(img.width(),  int(vr.width()  * lod) + 1))
        th = max(1, min(img.height(), int(vr.height() * lod) + 1))
        small = img.scaled(tw, th, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._frame_pixmap = QPixmap.fromImage(small)
        self._scaled_cache = None       # invalidate
        self._frame_pending = True
        self._last_lod = lod
        self.update()

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = duration

    def _on_position_changed(self, position: int) -> None:
        try:
            if self._destroyed:
                return
            self._position_ms = position
            # Sync play/pause sticker to actual player state
            playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            if hasattr(self, '_play_btn') and self._play_btn._in_confirm != playing:
                self._play_btn._in_confirm = playing
                self._play_btn.update()
            self.update()
        except RuntimeError:
            return

    def _toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        elif self._viewport_visible:
            self._player.play()
        self.update()

    def _toggle_loop(self) -> None:
        self.data.looping = not self.data.looping

    def _toggle_mute(self) -> None:
        self.data.muted = not self.data.muted
        self._audio.setMuted(self.data.muted)

    def _toggle_border(self) -> None:
        self.data.show_border = not self.data.show_border
        self.update()

    def _stop(self) -> None:
        self._player.stop()
        self.update()

    def _scrub_to(self, x: float) -> None:
        """Seek to position based on x coordinate within the progress bar."""
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        target = int(ratio * self._duration_ms)
        self._player.setPosition(target)

    def _volume_scrub_to(self, y: float) -> None:
        """Set volume based on y coordinate within the volume slider.
        Bottom = 0 (silent), top = 1 (full) — gradient flows upward."""
        vr = self._volume_rect()
        ratio = 1.0 - max(0.0, min(1.0, (y - vr.top()) / max(1.0, vr.height())))
        self._target_volume = ratio
        self._audio.setVolume(ratio)
        self.data.volume = int(ratio * 100)
        self.update()

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

        # Mute toggle — emoji faces, matches AudioNode
        self._mute_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001fae2" if self.data.muted else "\U0001f60a",  # 🫢 / 😊
            set_emoji=lambda _: self._toggle_mute(),
        )
        self._mute_btn.setToolTip("Mute" if not self.data.muted else "Unmute")
        self._buttons.append(self._mute_btn)

        # Play/pause — sticker toggle
        play_pix  = Theme.icon(Theme.iconPlayIconic,  fallback_color="#9a7abf")
        pause_pix = Theme.icon(Theme.iconPauseIconic, fallback_color="#9a7abf")
        self._play_btn = NodeButton(
            self, play_pix, self._toggle_playback,
            pixmap_confirm=pause_pix, toggle=True,
        )
        self._play_btn._sticker_shadow = True
        self._play_btn.setToolTip("Play / Pause")
        self._buttons.append(self._play_btn)

        # Loop toggle — sticker icons: return arrow (off / direct playback) / loop arrow (on)
        loop_off_pix = Theme.icon(Theme.iconReturnIconic, fallback_color="#9a7abf")
        loop_on_pix  = Theme.icon(Theme.iconLoopAudio,    fallback_color="#9a7abf")
        self._loop_btn = NodeButton(
            self, loop_off_pix, self._toggle_loop,
            pixmap_confirm=loop_on_pix, toggle=True,
        )
        self._loop_btn._sticker_shadow = True
        self._loop_btn._in_confirm = self.data.looping
        self._loop_btn.setToolTip("Loop: on" if self.data.looping else "Loop: off")
        self._buttons.append(self._loop_btn)

        # Border toggle — simple circle, state is visible on the node itself
        self._border_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u25cb",  # ○
            set_emoji=lambda _: self._toggle_border(),
        )
        self._border_btn.setToolTip("Toggle ivory border")
        self._buttons.append(self._border_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    # ── Resize-driven shelf reveal (mirrors AboutNode) ───────────────────────
    # Asymmetric thresholds: reveal demands a deliberate yank so a casual
    # height nudge doesn't surface the shelf by accident; hide is lighter so
    # the user can dial the final height down without the shelf clinging.
    # Same values AboutNode uses — the gesture feels the same on both nodes.
    _RESIZE_SHELF_REVEAL_THRESHOLD = 75.0
    _RESIZE_SHELF_HIDE_THRESHOLD   = 30.0

    def mouseDoubleClickEvent(self, event) -> None:
        if self._video_rect().contains(event.pos()):
            if self.data.source_path:
                self._toggle_playback()
            else:
                self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        # Seed the shelf anchor at the start of any drag so the resize-driven
        # threshold check measures from press-time height. Done unconditionally
        # so a press anywhere on the node primes the gesture.
        self._shelf_anchor_h = self.rect().height()

        pos = event.pos()
        if self._buttons_visible and event.button() == Qt.LeftButton:
            if self._volume_rect().contains(pos):
                self._volume_scrubbing = True
                self._volume_scrub_to(pos.y())
                event.accept()
                return
            # The resize handle lives in the bottom-right corner. Skip our
            # own progress-scrub handling inside the resize zone so super()
            # (BaseNode) gets the click and starts a resize. Without this,
            # progress scrub eats every corner click and resize is dead.
            rect = self.rect()
            grip = self._resize_grip
            in_resize_zone = (
                pos.x() >= rect.right()  - grip
                and pos.y() >= rect.bottom() - grip
            )
            if not in_resize_zone and self._progress_rect().contains(pos):
                self._scrubbing = True
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
        if self._volume_scrubbing and event.buttons() & Qt.LeftButton:
            self._volume_scrub_to(event.pos().y())
            event.accept()
            return
        if self._scrubbing and event.buttons() & Qt.LeftButton:
            self._scrub_to(event.pos().x())
            event.accept()
            return

        # Defer to BaseNode first so the resize actually happens and
        # self.rect() reflects the updated geometry before we inspect it.
        super().mouseMoveEvent(event)

        # ── Bidirectional shelf coupling via resize ───────────────────────
        # Resize direction drives shelf state:
        #   • growing taller past the reveal threshold → reveal
        #   • shrinking shorter past the hide threshold → hide
        # Anchor is re-seeded after every toggle so a single continuous
        # drag can flip the shelf multiple times.
        if not self._is_resizing:
            return
        if self._shelf_anchor_h is None:
            self._shelf_anchor_h = self.rect().height()
        delta_h = self.rect().height() - self._shelf_anchor_h
        if not self._buttons_visible and delta_h > self._RESIZE_SHELF_REVEAL_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()
        elif self._buttons_visible and delta_h < -self._RESIZE_SHELF_HIDE_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()

    def mouseReleaseEvent(self, event) -> None:
        if self._volume_scrubbing and event.button() == Qt.LeftButton:
            self._volume_scrubbing = False
            event.accept()
            return
        if self._scrubbing and event.button() == Qt.LeftButton:
            self._scrubbing = False
            if self._was_playing and self._viewport_visible:
                self._player.play()
                self._was_playing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
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
        """
        LOD-aware content tier — ingest-time sizing, not paint-time.

        Unlike ImageNode (static source, resized per paint), video frames
        are ephemeral: each one is already sized to screen-pixel resolution
        by _on_frame using the current view LOD, capped at source res.
        Paint therefore only aspect-fits and draws — no heavy rescale.

        Paused videos are the one case the ingest path cannot cover on its
        own: no new frame arrives to pick up a zoom change. So a detected
        LOD delta past a quantized 0.5 step fires a setPosition nudge to
        re-emit the current frame at the new size. Playing videos catch
        up naturally on the next decoded frame.
        """
        painter.save()

        vr = self._video_rect()
        pr = self._progress_rect()

        self._frame_pending = False          # allow next frame to be accepted

        # ── Paused-video LOD refresh ─────────────────────────────────────────
        # Playing videos pick up zoom changes automatically on the next frame
        # (16-33ms). Paused videos must be asked — re-emit the current frame
        # via a zero-distance setPosition so _on_frame fires with the new LOD.
        # Guarded on a meaningful LOD delta so ordinary panning/hover doesn't
        # thrash the decoder.
        try:
            raw_lod = max(1.0, abs(painter.worldTransform().m11()))
            cur_lod = max(1.0, math.ceil(raw_lod * 2.0) / 2.0)
            if (cur_lod != self._last_lod
                    and self._frame_pixmap is not None
                    and self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState):
                self._last_lod = cur_lod   # latch immediately so we don't re-fire
                QTimer.singleShot(0, lambda: self._player.setPosition(self._player.position()))
        except RuntimeError:
            pass

        if self._frame_pixmap and not self._frame_pixmap.isNull():
            # ── Clip to rounded rect ─────────────────────────────────────────
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(vr, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            # ── Scale + centre ───────────────────────────────────────────────
            # _frame_pixmap is already LOD-sized from _on_frame; scaled_cache
            # just aspect-fits it to vr for draw. Enable SmoothPixmapTransform
            # so any residual painter-side upsample (between zoom steps) is
            # bilinear, not nearest-neighbour.
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

            # ── Border ────────────────────────────────────────────────────────
            bevel_r = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            painter.setBrush(Qt.NoBrush)
            if self.data.show_border:
                # Ivory white border — sits inside the video rect
                painter.setPen(QPen(QColor(225, 213, 198, 255), 3))
                painter.drawRoundedRect(
                    vr.adjusted(1, 1, -1, -1), bevel_r, bevel_r,
                )
            else:
                # Default subtle bevel
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

        # ── Progress bar + volume slider (only when button row is visible) ────
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

            # End-of-bar marker — short vertical tick at the right edge of
            # the progress bar so the truncation (made room for resize) is
            # legible. Same shape as AudioNode's marker; placeholder visual
            # until a finer cue is authored.
            marker_pen = QPen(QColor(Theme.textPrimary), 3)
            painter.setPen(marker_pen)
            painter.setBrush(Qt.NoBrush)
            end_x = pr.right()
            painter.drawLine(
                int(end_x), int(pr.top()    - 4),
                int(end_x), int(pr.bottom() + 4),
            )

            # ── Volume slider (vertical, left of video) ──────────────────────
            vol_r = self._volume_rect()
            painter.setBrush(bar_bg)
            painter.drawRoundedRect(vol_r, 3, 3)

            vol_ratio = self._target_volume
            fill_h = vol_r.height() * vol_ratio
            if fill_h > 0:
                fill_rect_v = QRectF(
                    vol_r.left(), vol_r.bottom() - fill_h,
                    vol_r.width(), fill_h,
                )
                vgrad = QLinearGradient(0, fill_rect_v.bottom(), 0, fill_rect_v.top())
                vgrad.setColorAt(0.0, QColor("#1e1e1e"))
                vgrad.setColorAt(0.4, QColor("#5c3e4f"))
                vgrad.setColorAt(0.7, QColor("#a56a85"))
                vgrad.setColorAt(1.0, QColor("#d87a9e"))
                painter.setBrush(vgrad)
                painter.drawRoundedRect(fill_rect_v, 3, 3)


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

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # VIEWPORT CULLING
    # ─────────────────────────────────────────────────────────────────────────

    def _set_viewport_visible(self, visible: bool) -> None:
        """Fade audio and pause/resume playback on visibility change.

        Fade-out (1 s) → pause when leaving view.
        Resume → fade-in (1 s) when entering view.
        Video pauses only after the fade completes so the audio tail
        never cuts mid-tone.
        """
        if visible == self._viewport_visible:
            return
        self._viewport_visible = visible
        if not self.data.source_path:
            return

        # Kill any in-flight fade before starting a new one
        if self._volume_anim:
            self._volume_anim.stop()
            self._volume_anim = None

        if visible:
            if self._was_playing_before_cull:
                self._audio.setVolume(0.0)
                self._player.play()
                self._was_playing_before_cull = False
                from utils.audio import audio as _audio_mgr
                if not _audio_mgr.is_muted():
                    self._fade_volume(0.0, self._target_volume)
        else:
            playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if playing:
                self._was_playing_before_cull = True
                self._fade_volume(self._audio.volume(), 0.0, pause_after=True)

    def _fade_volume(self, start: float, end: float, pause_after: bool = False) -> None:
        """Animate QAudioOutput.volume over 1 second, optionally pausing when done."""
        self._volume_anim = QPropertyAnimation(self._audio, b"volume")
        self._volume_anim.setDuration(1000)
        self._volume_anim.setStartValue(start)
        self._volume_anim.setEndValue(end)
        self._volume_anim.setEasingCurve(QEasingCurve.InOutQuad)
        if pause_after:
            self._volume_anim.finished.connect(self._pause_after_fade)
        self._volume_anim.start()

    def _pause_after_fade(self) -> None:
        """Called when the fade-out finishes — now safe to pause the player."""
        if self._destroyed:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _quiet_for_shake(self) -> None:
        """Sever the media pipeline synchronously at shake-trigger time.

        Why this matters on corrupted media: the particle burst + deferred
        removeItem leaves an 8000-sprite window during which the player
        keeps decoding. On a malformed file, WMF's async decoder thread
        may be stuck mid-parse on bad bitstream data — leaving it running
        during the burst gives it more opportunity to dereference
        partially-freed pipeline state once teardown finally begins.

        ``setSource(QUrl())`` is the single most important step: it tells
        WMF to flush the decoder for *this* source while Python and Qt
        are both fully alive. By the time ``_demolition_pre`` runs, the
        player has no active source and ``stop`` / ``deleteLater`` are
        quiet operations.

        Kept separate from ``_demolition_pre`` because shake-delete runs
        this immediately but the rest of teardown is deferred until
        mouseRelease + particle animation completes.
        """
        for _obj in (self._player, self._sink, self._audio):
            if _obj is not None:
                try: _obj.blockSignals(True)
                except (RuntimeError, AttributeError): pass
        # Detach from the source FIRST — this is what flushes the WMF
        # decoder thread. Without it, stop() on a corrupted stream can
        # race the decoder's own error-handling path and crash inside
        # WMF before Qt ever emits a signal we could catch.
        if self._player is not None:
            try: self._player.setSource(QUrl())
            except (RuntimeError, AttributeError): pass
            try: self._player.stop()
            except (RuntimeError, AttributeError): pass

    # Crew sets _destroyed FIRST so background ingest/drift workers
    # bail before any Qt teardown writes to dead state.
    _demolition_thread_flag = '_destroyed'
    _demolition_timers = [('_cache_poll', '_check_cache_delivery')]
    _demolition_animations = [('_volume_anim', ['finished'])]
    # Media-player linkage is bespoke (we also need to null the sink
    # and audio deleteLater), so we don't use _demolition_media_players
    # directly — keep the sequence in _demolition_pre for clarity.

    def _demolition_pre(self) -> None:
        # Null pending fields — the background thread has already bailed
        # via the _destroyed flag that the crew set; anything still
        # in-flight is safe to drop.
        self._pending_cache_key = None
        self._pending_drift     = None
        self._pending_size      = None
        self._pending_mtime     = None

        # ── Block signals on all three Qt objects FIRST ──────────────────
        # Nothing can queue a new event during teardown regardless of
        # whether we know about the signal. This covers QMediaPlayer's
        # internal emissions (playbackStateChanged, errorOccurred,
        # bufferProgress, sourceChanged, etc.) that we never connected to
        # but Qt / the WMF backend might still fire — those queued events
        # processed after deleteLater would land on freed memory and
        # trigger STATUS_HEAP_CORRUPTION (0xc0000374) in ntdll.
        for _obj in (self._player, self._sink, self._audio):
            if _obj is not None:
                try: _obj.blockSignals(True)
                except (RuntimeError, AttributeError): pass

        # Fade volume to zero before the player stop so the audio sink
        # drains cleanly. Signals are blocked so no slot fires.
        if self._audio is not None:
            try: self._audio.setVolume(0.0)
            except (RuntimeError, AttributeError): pass

        # Nuke ALL signal connections on each object — belt-and-suspenders
        # alongside blockSignals above. .disconnect() with no args drops
        # every outgoing connection in one call, no need to enumerate.
        for _obj in (self._player, self._sink, self._audio):
            if _obj is not None:
                try: _obj.disconnect()
                except (RuntimeError, TypeError): pass

        # Sever the media pipeline synchronously — the deferred
        # singleShot(0) used to leave a window where the player delivered
        # a frame to a dead sink.
        if self._player is not None:
            # Detach the source BEFORE stop(). On corrupted media,
            # stop() can race the WMF decoder thread's error-handling
            # path; clearing the source flushes the decoder first and
            # makes stop() a quiet no-op. Idempotent with _quiet_for_shake,
            # which already ran for shake-delete but not for other
            # teardown paths (scene switch, group delete via session
            # load, etc.).
            try: self._player.setSource(QUrl())
            except (RuntimeError, AttributeError): pass
            try: self._player.stop()
            except (RuntimeError, AttributeError): pass
            try: self._player.setVideoOutput(None)
            except (RuntimeError, AttributeError): pass
            try: self._player.setAudioOutput(None)
            except (RuntimeError, AttributeError): pass

        # Schedule C++ deletion — survives beyond the Python ref drop below.
        for _obj in (self._player, self._sink, self._audio):
            if _obj is not None:
                try: _obj.deleteLater()
                except (RuntimeError, AttributeError): pass

        # Drop Python wrapper refs so any code on the main thread that
        # references self._player post-teardown gets a clean AttributeError
        # instead of dereferencing a dangling pointer into freed memory.
        # Order matters: null refs AFTER deleteLater so Qt still has a
        # valid pointer when scheduling the cleanup.
        self._player = None
        self._sink = None
        self._audio = None

        self._volume_anim = None

    def _demolition_post(self) -> None:
        self._frame_pixmap = None
        self._scaled_cache = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        # Every read here uses getattr-with-default so to_dict can never raise,
        # even on a partially-initialised node. Swallowing here caused videos
        # to silently drop from the clipboard copy on at least one first
        # attempt (2026-04-21) — non-reproducible race, but the class of "one
        # missing attribute makes the whole serialize fail" is closed now.
        # self.data.* fields fall through to whatever was loaded from session
        # or set earlier, which is always preferable to raising.
        pos_ms = getattr(self, '_position_ms', None)
        if pos_ms is not None:
            self.data.playback_pos = int(pos_ms)
        vol = getattr(self, '_target_volume', None)
        if vol is not None:
            try: self.data.volume = int(vol * 100)
            except (TypeError, ValueError): pass
        # Guard Qt probes — post-teardown these are None (see _demolition_pre),
        # and session save can still hit to_dict on a removed-but-not-yet-GC'd
        # node. Fall through to the existing data values in that case.
        audio = getattr(self, '_audio', None)
        if audio is not None:
            try: self.data.muted = audio.isMuted()
            except (RuntimeError, AttributeError): pass
        player = getattr(self, '_player', None)
        if player is not None:
            try:
                self.data.was_playing = (
                    player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                    or getattr(self, '_was_playing_before_cull', False)
                )
            except (RuntimeError, AttributeError): pass
        try:
            self.sync_data()
        except Exception:
            # Partial-init catch — don't let sync_data failure drop the node
            # from a clipboard copy; the data fields already carry the saved
            # session values which are good enough to reconstruct elsewhere.
            pass
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'VideoNode':
        return VideoNode(VideoNodeData.from_dict(data))
