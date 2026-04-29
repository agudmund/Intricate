#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AudioNode.py AudioNode class
-A compact audio player node for WAV, MP3, FLAC and friends for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import QFileDialog
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from shiboken6 import isValid as _shiboken_isValid

from nodes.BaseNode import BaseNode
from data.AudioNodeData import AudioNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("audio_node")

_AUDIO_EXTENSIONS = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma)"


class AudioNode(BaseNode):
    _has_depth_toggle = True
    """
    Compact audio player node.

    Drop an audio file or browse to load. Play/pause via double-click
    on the body area. Mute and loop toggles on the button row.
    """

    def __init__(self, data: AudioNodeData | None = None):
        if data is None:
            data = AudioNodeData()
        super().__init__(data)

        # ── Media pipeline ────────────────────────────────────────────────
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._player.setAudioOutput(self._audio)

        self._audio.setVolume(data.volume / 100.0)
        from utils.audio import audio as _audio_mgr
        self._audio.setMuted(data.muted or _audio_mgr.is_muted())

        self._target_volume = data.volume / 100.0
        self._duration_ms   = 0
        self._position_ms   = 0
        self._restore_pos   = 0
        self._scrubbing          = False
        self._volume_scrubbing   = False
        self._viewport_visible   = True
        self._was_playing_before_cull = False
        self._vol_anim = None

        self._player.durationChanged.connect(self._on_duration)
        self._player.positionChanged.connect(self._on_position)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # ── Visual ────────────────────────────────────────────────────────
        c = QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutTransparency)
        self.setBrush(c)
        self._apply_depth()

        # ── Restore source if session had one ─────────────────────────────
        if data.source_path:
            p = Path(data.source_path)
            if p.exists():
                self._set_source(p, restore_pos=data.playback_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # MEDIA
    # ─────────────────────────────────────────────────────────────────────────

    def _set_source(self, path: Path, restore_pos: int = 0) -> None:
        self.data.source_path = str(path.resolve())
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._player.setLoops(QMediaPlayer.Loops.Infinite if self.data.looping else 1)
        if restore_pos > 0:
            self._restore_pos = restore_pos

    def load_from_path(self, path: str | Path) -> None:
        """Load an audio file. Public — called by file browser and View.dropEvent."""
        path = Path(path)
        if not path.exists():
            return
        self._set_source(path)
        if not self.data.caption:
            self.data.caption = path.stem
        self.data.title = self.data.caption or "Audio"

        # Auto-size width to fit the title text
        from PySide6.QtGui import QFontMetrics
        _f = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        _f.setStyleName("MediumOblique")
        fm = QFontMetrics(_f)
        text_w = fm.horizontalAdvance(self.data.title) + self._CONTENT_PAD * 2 + 20
        min_w = max(self.data.width, text_w)
        if min_w > self.rect().width():
            r = self.rect()
            self.setRect(QRectF(r.x(), r.y(), min_w, r.height()))
            self.data.width = min_w

        self.update()

    # ── Cross-thread slot guard ──────────────────────────────────────────────
    # QMediaPlayer runs its decoder on its own thread; positionChanged,
    # durationChanged and mediaStatusChanged are queued across threads into
    # the GUI thread. The demolition crew disconnects them during teardown,
    # but Qt does not cancel *already-queued* meta-call events. So an
    # in-flight position tick can still land on the dead Python wrapper and
    # dereference its C++ half — an access violation in Qt6Core. Guard
    # every cross-thread slot with shiboken validity so late arrivals return
    # silently. Disconnect is still the primary defence; this is the net.
    def _on_duration(self, ms: int) -> None:
        if not _shiboken_isValid(self):
            return
        self._duration_ms = ms

    def _on_position(self, ms: int) -> None:
        if not _shiboken_isValid(self):
            return
        self._position_ms = ms
        self.update()

    def _on_media_status(self, status) -> None:
        if not _shiboken_isValid(self):
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self._restore_pos > 0:
                self._player.setPosition(self._restore_pos)
                self._restore_pos = 0
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.data.looping and self._player.loops() == 1:
                # Fallback — shouldn't fire when loops=Infinite, but just in case
                self._loop_restart()

    # ─────────────────────────────────────────────────────────────────────────
    # CONTROLS
    # ─────────────────────────────────────────────────────────────────────────

    def _fade_volume(self, start: float, end: float, duration: int = 300,
                     on_finish=None) -> None:
        """Animate QAudioOutput.volume for smooth transitions."""
        self._vol_anim = QPropertyAnimation(self._audio, b"volume")
        self._vol_anim.setDuration(duration)
        self._vol_anim.setStartValue(start)
        self._vol_anim.setEndValue(end)
        self._vol_anim.setEasingCurve(QEasingCurve.InOutQuad)
        if on_finish:
            self._vol_anim.finished.connect(on_finish)
        self._vol_anim.start()

    def _loop_restart(self) -> None:
        """Fade out → seek to 0 → fade in to avoid loop clipping."""
        def _restart():
            self._player.setPosition(0)
            self._player.play()
            self._fade_volume(0.0, self._target_volume)
        self._fade_volume(self._audio.volume(), 0.0, duration=600, on_finish=_restart)

    def _toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
        self.update()

    def _toggle_mute(self) -> None:
        self.data.muted = not self.data.muted
        if self.data.muted:
            self._fade_volume(self._audio.volume(), 0.0, duration=300,
                              on_finish=lambda: self._audio.setMuted(True))
        else:
            self._audio.setMuted(False)
            self._fade_volume(0.0, self._target_volume)

    def _toggle_loop(self) -> None:
        self.data.looping = not self.data.looping
        self._player.setLoops(QMediaPlayer.Loops.Infinite if self.data.looping else 1)
        self._loop_btn.setToolTip("Loop: on" if self.data.looping else "Loop: off")
        self._loop_btn.update()

    def _split_at_playhead(self) -> None:
        """Split the audio file at the current playhead position into two files.

        Uses ffmpeg for lossless splitting. Creates two new AudioNodes in the
        scene — part A (start to playhead) and part B (playhead to end).
        """
        if not self.data.source_path or self._duration_ms <= 0 or self._position_ms <= 0:
            return
        if self._position_ms >= self._duration_ms:
            return

        import subprocess as _sp
        src = Path(self.data.source_path)
        if not src.exists():
            return

        # Was playing? Pause first.
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if was_playing:
            self._player.pause()

        split_ms = self._position_ms
        split_s  = split_ms / 1000.0
        stem     = src.stem
        ext      = src.suffix

        part_a = src.parent / f"{stem}_A{ext}"
        part_b = src.parent / f"{stem}_B{ext}"

        # Avoid overwriting — append number if exists
        counter = 2
        while part_a.exists():
            part_a = src.parent / f"{stem}_A_{counter}{ext}"
            counter += 1
        counter = 2
        while part_b.exists():
            part_b = src.parent / f"{stem}_B_{counter}{ext}"
            counter += 1

        try:
            # Part A: start to split point
            _sp.run([
                "ffmpeg", "-y", "-i", str(src),
                "-t", f"{split_s:.3f}",
                "-c", "copy", str(part_a),
            ], capture_output=True, check=True)

            # Part B: split point to end
            _sp.run([
                "ffmpeg", "-y", "-i", str(src),
                "-ss", f"{split_s:.3f}",
                "-c", "copy", str(part_b),
            ], capture_output=True, check=True)
        except Exception as e:
            _log.warning(f"[AudioNode] split failed: {e}")
            return

        # Spawn two new AudioNodes in the scene
        scene = self.scene()
        if not scene or not hasattr(scene, 'add_audio_node'):
            return

        my_pos = self.pos()
        offset_y = self.rect().height() + 30

        node_a = scene.add_audio_node(pos=my_pos + QPointF(0, offset_y))
        node_a.load_from_path(str(part_a))

        node_b = scene.add_audio_node(pos=my_pos + QPointF(0, offset_y * 2))
        node_b.load_from_path(str(part_b))

        _log.info(f"[AudioNode] split '{stem}' at {split_s:.3f}s → {part_a.name}, {part_b.name}")

    def _open_file_browser(self) -> None:
        win = self._lower_window()
        was_collapsed = False
        mw = None
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
                    was_collapsed = True
        except Exception:
            pass
        if mw is not None:
            try:
                mw.activateWindow()
                mw.raise_()
            except Exception:
                pass
        scene = self.scene()
        start_dir = scene.get_browse_dir("audio") if scene else ""
        path, _ = QFileDialog.getOpenFileName(
            mw, "Select Audio", start_dir, _AUDIO_EXTENSIONS
        )
        if was_collapsed and mw is not None:
            try:
                mw.toggle_curtains()
            except Exception:
                pass
        self._raise_window(win)
        if path:
            if scene:
                scene.remember_browse_dir("audio", str(Path(path).parent))
            self.load_from_path(path)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton, EmojiButton

        super()._build_buttons()

        # Mute toggle — emoji faces
        self._mute_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001fae2" if self.data.muted else "\U0001f60a",  # 🫢 / 😊
            set_emoji=lambda _: self._toggle_mute(),
        )
        self._mute_btn.setToolTip("Mute" if not self.data.muted else "Unmute")
        self._buttons.append(self._mute_btn)

        # Play/pause
        # Play/pause moved to the status line — click the ▶/‖ area to toggle

        # Split at playhead — sticker icon
        trim_pix = Theme.icon(Theme.iconTrimAudio, fallback_color="#b0b0b0")
        self._split_btn = NodeButton(self, trim_pix, self._split_at_playhead)
        self._split_btn._sticker_shadow = True
        self._split_btn.setToolTip("Split at playhead")
        self._buttons.append(self._split_btn)

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

    # ─────────────────────────────────────────────────────────────────────────
    # PROGRESS BAR + SCRUB
    # ─────────────────────────────────────────────────────────────────────────

    _PROGRESS_H = 6.0
    _PROGRESS_PAD = 8.0
    _VOL_SLIDER_W = 6.0   # matches progress bar height for visual pairing

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        vol_reserve = self._VOL_SLIDER_W + self._PROGRESS_PAD
        return QRectF(
            r.x() + self._PROGRESS_PAD + vol_reserve,
            r.bottom() - self._PROGRESS_H - self._PROGRESS_PAD,
            r.width() * 0.66 - vol_reserve,
            self._PROGRESS_H,
        )

    def _volume_rect(self) -> QRectF:
        """Vertical volume slider — left edge, from body top to progress bar bottom."""
        r = self.rect()
        top = r.y() + self._body_top()
        pr = self._progress_rect()
        return QRectF(
            r.x() + self._PROGRESS_PAD,
            top,
            self._VOL_SLIDER_W,
            pr.bottom() - top,
        )

    def _scrub_to(self, x: float) -> None:
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._player.setPosition(int(ratio * self._duration_ms))
        if not was_playing:
            self._player.pause()

    def _volume_scrub_to(self, y: float) -> None:
        """Set volume based on y coordinate within the volume slider."""
        vr = self._volume_rect()
        ratio = 1.0 - max(0.0, min(1.0, (y - vr.top()) / max(1.0, vr.height())))
        self._target_volume = ratio
        self._audio.setVolume(ratio)
        self.data.volume = int(ratio * 100)
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._progress_rect().contains(event.pos()):
            event.accept()
            return
        # Only open file browser if no audio is loaded yet
        if not self.data.source_path:
            self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._volume_rect().contains(event.pos()):
            self._volume_scrubbing = True
            self._volume_scrub_to(event.pos().y())
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._progress_rect().contains(event.pos()):
            self._scrubbing = True
            self._scrub_to(event.pos().x())
            event.accept()
            return
        # Click on the status area — play/pause (▶/‖) or restart (⏮)
        if event.button() == Qt.LeftButton and self.data.source_path and self._duration_ms > 0:
            r = self.rect()
            pad = self._CONTENT_PAD
            body_y = r.top() + self._body_top()
            prog_y = self._progress_rect().top()
            pos = event.pos()
            if body_y <= pos.y() < prog_y:
                btn_left = r.left() + pad
                if btn_left <= pos.x() < btn_left + 24:
                    # Play/pause button zone
                    self._toggle_playback()
                    event.accept()
                    return
                elif btn_left + 24 <= pos.x() < btn_left + 52:
                    # Restart button zone
                    self._player.setPosition(0)
                    self._player.play()
                    self.update()
                    event.accept()
                    return
        self._scrubbing = False
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
        self._scrubbing = False
        super().mouseReleaseEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r   = self.rect()
        pad = self._CONTENT_PAD
        top = self._content_top()

        # Title
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        label = self.data.caption or self.data.title
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            label,
        )

        # Status line
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.7)
        y = r.top() + self._body_top()

        if not self.data.source_path:
            status = "Double-click to browse for audio"
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                status,
            )
        elif self._duration_ms > 0:
            pos_s = self._position_ms // 1000
            dur_s = self._duration_ms // 1000
            playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

            # Play/Pause button: ▶ or ‖  |  Restart button: ⏮
            pp_icon = "\u2016" if playing else "\u25b6"   # ‖ / ▶
            restart_icon = "\u23ee"                       # ⏮
            pos_ms_frac = self._position_ms % 1000
            dur_ms_frac = self._duration_ms % 1000
            time_str = f"{pos_s // 60}:{pos_s % 60:02d}.{pos_ms_frac:03d} / {dur_s // 60}:{dur_s % 60:02d}.{dur_ms_frac:03d}"

            x = r.left() + pad
            # Draw transport icons at title font size for visibility at zoom
            icon_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + 4))
            painter.setFont(icon_font)
            painter.drawText(QRectF(x, y - 2, 24, 24), Qt.AlignLeft | Qt.AlignVCenter, pp_icon)
            x += 24
            painter.drawText(QRectF(x, y - 2, 24, 24), Qt.AlignLeft | Qt.AlignVCenter, restart_icon)
            x += 28
            # Switch back to body font for time string
            painter.setFont(body_font)
            painter.drawText(QRectF(x, y, r.width() - pad - x + r.left(), 20),
                             Qt.AlignLeft | Qt.AlignTop, time_str)
        else:
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                "Ready",
            )

        # ── Progress bar (always visible) ────────────────────────────────
        painter.setOpacity(1.0)
        pr = self._progress_rect()
        bar_bg = QColor(Theme.nodeBg).lighter(130)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bar_bg)
        painter.drawRoundedRect(pr, 3, 3)

        if self._duration_ms > 0:
            ratio = self._position_ms / self._duration_ms
            fill_rect = QRectF(pr.left(), pr.top(), pr.width() * ratio, pr.height())
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            grad.setColorAt(0.0, QColor("#1e1e1e"))
            grad.setColorAt(0.4, QColor("#5c3e4f"))
            grad.setColorAt(0.7, QColor("#a56a85"))
            grad.setColorAt(1.0, QColor("#d87a9e"))
            painter.setBrush(grad)
            painter.drawRoundedRect(fill_rect, 3, 3)

        # End-of-bar marker — tall vertical line at the right edge
        from PySide6.QtGui import QPen
        marker_pen = QPen(QColor(Theme.textPrimary), 3)
        painter.setPen(marker_pen)
        painter.setBrush(Qt.NoBrush)
        end_x = pr.right()
        painter.drawLine(
            int(end_x), int(pr.top() - 10),
            int(end_x), int(pr.bottom() + 10),
        )

        # ── Volume slider (vertical, left of body) ──────────────────────
        painter.setPen(Qt.NoPen)
        vol_r = self._volume_rect()
        painter.setBrush(bar_bg)
        painter.drawRoundedRect(vol_r, 3, 3)

        vol_ratio = self._target_volume
        fill_h = vol_r.height() * vol_ratio
        if fill_h > 0:
            fill_v = QRectF(vol_r.left(), vol_r.bottom() - fill_h,
                            vol_r.width(), fill_h)
            vgrad = QLinearGradient(0, fill_v.bottom(), 0, fill_v.top())
            vgrad.setColorAt(0.0, QColor("#1e1e1e"))
            vgrad.setColorAt(0.4, QColor("#5c3e4f"))
            vgrad.setColorAt(0.7, QColor("#a56a85"))
            vgrad.setColorAt(1.0, QColor("#d87a9e"))
            painter.setBrush(vgrad)
            painter.drawRoundedRect(fill_v, 3, 3)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # VIEWPORT CULLING
    # ─────────────────────────────────────────────────────────────────────────

    def _set_viewport_visible(self, visible: bool) -> None:
        """Fade audio and pause/resume playback on visibility change.

        Same spatial awareness as VideoNode — only render what's in front
        of the listener's ears.  Fade-out → pause when leaving view,
        resume → fade-in when entering view.
        """
        if visible == self._viewport_visible:
            return
        self._viewport_visible = visible
        if not self.data.source_path:
            return

        # Kill any in-flight fade before starting a new one
        if hasattr(self, '_vol_anim') and self._vol_anim:
            self._vol_anim.stop()
            self._vol_anim = None

        if visible:
            if self._was_playing_before_cull:
                self._audio.setVolume(0.0)
                self._player.play()
                self._was_playing_before_cull = False
                from utils.audio import audio as _audio_mgr
                if not _audio_mgr.is_muted():
                    self._fade_volume(0.0, self._target_volume, duration=1000)
        else:
            playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if playing:
                self._was_playing_before_cull = True
                self._fade_volume(
                    self._audio.volume(), 0.0, duration=1000,
                    on_finish=self._pause_after_fade,
                )

    def _pause_after_fade(self) -> None:
        """Called when the fade-out finishes — now safe to pause."""
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    # Volume anim declared; media-player linkage is bespoke — we sever
    # player → audio synchronously in the pre-hook (mirrors VideoNode's
    # 2026-04-16 canonical pattern).  Deferred stop via singleShot(0)
    # left a window where the decoder thread delivered a queued
    # positionChanged / mediaStatusChanged into a dead AudioNode,
    # tripping shiboken "Internal C++ object already deleted".
    _demolition_animations = [('_vol_anim', ['finished'])]

    def _demolition_pre(self) -> None:
        # ── Block signals on both Qt objects FIRST ───────────────────────
        # Nothing queues a new event during teardown regardless of whether
        # we know about the signal. Covers QMediaPlayer's internal
        # emissions (playbackStateChanged, errorOccurred, bufferProgress,
        # sourceChanged, etc.) that we never connected to but Qt / the
        # WMF backend might still fire — those queued events processed
        # after deleteLater would land on freed memory and trigger
        # STATUS_HEAP_CORRUPTION (0xc0000374) in ntdll.
        for _obj in (self._player, self._audio):
            if _obj is not None:
                try: _obj.blockSignals(True)
                except (RuntimeError, AttributeError): pass

        # Volume → 0 first so the audio sink drains cleanly before we
        # tear down the player. Signals are blocked so no slot fires.
        if self._audio is not None:
            try: self._audio.setVolume(0.0)
            except (RuntimeError, AttributeError): pass

        # Nuke ALL signal connections on each object — belt-and-suspenders
        # alongside blockSignals above. .disconnect() with no args drops
        # every outgoing connection in one call.
        for _obj in (self._player, self._audio):
            if _obj is not None:
                try: _obj.disconnect()
                except (RuntimeError, TypeError): pass

        # Synchronous stop + sever + deleteLater — the canonical pattern
        # from VideoNode 2026-04-21.
        if self._player is not None:
            try: self._player.stop()
            except (RuntimeError, AttributeError): pass
            try: self._player.setAudioOutput(None)
            except (RuntimeError, AttributeError): pass

        for _obj in (self._player, self._audio):
            if _obj is not None:
                try: _obj.deleteLater()
                except (RuntimeError, AttributeError): pass

        # Drop Python wrapper refs so any post-teardown reference gets a
        # clean AttributeError instead of dereferencing a dangling pointer.
        # Order: null refs AFTER deleteLater so Qt still has a valid
        # pointer when scheduling cleanup.
        self._player = None
        self._audio = None

        self._vol_anim = None

    def to_dict(self) -> dict:
        # getattr-with-default on every read so to_dict cannot raise on a
        # partially-initialised node — mirrors VideoNode 2026-04-21 defence
        # against the clipboard-copy intermittent-drop class.
        pos_ms = getattr(self, '_position_ms', None)
        if pos_ms is not None:
            self.data.playback_pos = int(pos_ms)
        vol = getattr(self, '_target_volume', None)
        if vol is not None:
            try: self.data.volume = int(vol * 100)
            except (TypeError, ValueError): pass
        audio = getattr(self, '_audio', None)
        if audio is not None:
            try: self.data.muted = audio.isMuted()
            except (RuntimeError, AttributeError): pass
        try:
            self.sync_data()
        except Exception:
            pass
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'AudioNode':
        return AudioNode(AudioNodeData.from_dict(d))
