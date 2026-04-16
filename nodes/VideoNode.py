#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/VideoNode.py VideoNode class
-Renders video with full playback inside the canvas via QMediaPlayer for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

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

    def __init__(self, data: VideoNodeData | None = None):
        if data is None:
            data = VideoNodeData()
        super().__init__(data)

        self._destroyed = False   # set by _prepare_for_removal to guard signal callbacks
        self._spawn_label = True  # set False to suppress caption AboutNode on load
        self._aspect_fitted = False  # True once we've auto-sized to the video's aspect ratio

        # ── Current frame pixmap ──────────────────────────────────────────────
        self._frame_pixmap: QPixmap | None = None
        self._scaled_cache: QPixmap | None = None
        self._scaled_cache_size: tuple[int, int] | None = None
        self._frame_pending: bool = False          # throttle: skip if paint hasn't caught up

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

        # Button row starts hidden — double-click the top strip to reveal
        self._buttons_visible = False
        self._anim_top_offset = 8.0
        for btn in self._buttons:
            btn.hide()

        # ── Restore from session ──────────────────────────────────────────────
        if data.source_path:
            p = Path(data.source_path)
            if p.exists():
                self._set_source(p, restore_pos=data.playback_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION → ABOUT NODE
    # ─────────────────────────────────────────────────────────────────────────

    def _top_offset(self) -> float:
        """Vertical space reserved above the video — full button zone or minimal pad."""
        return _BUTTON_ZONE_H if self._buttons_visible else 15.0

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        vol_reserve = PROGRESS_HEIGHT + VIDEO_PADDING if self._buttons_visible else 0.0
        return QRectF(
            r.x() + VIDEO_PADDING + vol_reserve,
            r.bottom() - PROGRESS_HEIGHT - VIDEO_PADDING,
            r.width() - VIDEO_PADDING * 2 - vol_reserve,
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
        """Load a video from a file path. Public — called by file browser and View.dropEvent."""
        path = Path(path)
        if not path.exists():
            return
        self._set_source(path)
        if not self.data.caption and self._spawn_label:
            self.data.caption = path.stem
            self._spawn_caption_node(path.stem)
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

    def _on_frame(self, frame: QVideoFrame) -> None:
        """Convert each video frame to a proxy-sized QPixmap for painting.

        We scale down immediately so only a thumbnail-sized pixmap lives in
        memory — never the full decoded frame.  If the previous frame hasn't
        been painted yet we drop this one entirely (frame-skip).
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

        # Scale to display size right away — never keep the full-res decode
        try:
            vr = self._video_rect()
        except RuntimeError:
            return
        tw, th = max(1, int(vr.width())), max(1, int(vr.height()))
        small = img.scaled(tw, th, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._frame_pixmap = QPixmap.fromImage(small)
        self._scaled_cache = None       # invalidate
        self._frame_pending = True
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

        # Loop toggle — sticker icons: direct arrow (off) / loop arrow (on)
        loop_off_pix = Theme.icon(Theme.iconDirectAudio, fallback_color="#9a7abf")
        loop_on_pix  = Theme.icon(Theme.iconLoopAudio,   fallback_color="#9a7abf")
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

    def mouseDoubleClickEvent(self, event) -> None:
        # Top strip above the video area — animated shelf toggle
        if event.pos().y() < self.rect().top() + self._top_offset():
            self._toggle_shelf()
            event.accept()
            return
        if self._video_rect().contains(event.pos()):
            if self.data.source_path:
                self._toggle_playback()
            else:
                self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.pos()
        if self._buttons_visible and event.button() == Qt.LeftButton:
            if self._volume_rect().contains(pos):
                self._volume_scrubbing = True
                self._volume_scrub_to(pos.y())
                event.accept()
                return
            if self._progress_rect().contains(pos):
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
        super().mouseMoveEvent(event)

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
        painter.save()

        vr = self._video_rect()
        pr = self._progress_rect()

        self._frame_pending = False          # allow next frame to be accepted

        if self._frame_pixmap and not self._frame_pixmap.isNull():
            # ── Clip to rounded rect ─────────────────────────────────────────
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - VIDEO_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(vr, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            # ── Scale + centre ───────────────────────────────────────────────
            # _frame_pixmap is already proxy-sized from _on_frame; only
            # re-scale if the node was resized since the last decode.
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

    def _prepare_for_removal(self) -> None:
        self._destroyed = True
        if self._volume_anim:
            try:
                self._volume_anim.finished.disconnect(self._pause_after_fade)
            except RuntimeError:
                pass
            self._volume_anim.stop()
            self._volume_anim = None
        self._audio.setVolume(0.0)
        try:
            self._sink.videoFrameChanged.disconnect(self._on_frame)
            self._player.durationChanged.disconnect(self._on_duration_changed)
            self._player.positionChanged.disconnect(self._on_position_changed)
            self._player.mediaStatusChanged.disconnect(self._on_media_status)
        except RuntimeError:
            pass  # already disconnected or C++ side gone
        # Stop synchronously and sever the sink → player link before GC
        # can collect them in the wrong order.  The deferred singleShot(0)
        # left a window where the player delivered a frame to a dead sink.
        self._player.stop()
        self._player.setVideoOutput(None)
        self._player.setAudioOutput(None)
        self._player.deleteLater()
        self._sink.deleteLater()
        self._audio.deleteLater()
        self._frame_pixmap = None
        self._scaled_cache = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.data.playback_pos = self._position_ms
        self.data.volume = int(self._target_volume * 100)
        self.data.muted = self._audio.isMuted()
        self.data.was_playing = (
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            or self._was_playing_before_cull
        )
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'VideoNode':
        return VideoNode(VideoNodeData.from_dict(data))
