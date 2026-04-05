#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AudioNode.py AudioNode class
-A compact audio player node for WAV, MP3, FLAC and friends for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import QFileDialog
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from nodes.BaseNode import BaseNode
from data.AudioNodeData import AudioNodeData
from graphics.Theme import Theme
from utils.logger import setup_logger
import utils.settings as settings

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

        self._player.durationChanged.connect(self._on_duration)
        self._player.positionChanged.connect(self._on_position)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # ── Visual ────────────────────────────────────────────────────────
        c = QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
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
        self.update()

    def _on_duration(self, ms: int) -> None:
        self._duration_ms = ms

    def _on_position(self, ms: int) -> None:
        self._position_ms = ms
        self.update()

    def _on_media_status(self, status) -> None:
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
        self._play_btn.update()
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

    def _open_file_browser(self) -> None:
        start_dir = settings.get_nested("node", "audio", "last_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Audio", start_dir, _AUDIO_EXTENSIONS
        )
        if path:
            settings.set_nested("node", "audio", "last_dir", str(Path(path).parent))
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
        self._play_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u2016" if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else "\u25b6",  # ‖ / ▶
            set_emoji=lambda _: self._toggle_playback(),
        )
        self._play_btn.setToolTip("Play / Pause")
        self._buttons.append(self._play_btn)

        # Loop toggle — plain arrows, no emoji background
        self._loop_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u21bb" if self.data.looping else "\u21a9",  # ↻ / ↩
            set_emoji=lambda _: self._toggle_loop(),
        )
        self._loop_btn.setToolTip("Loop: on" if self.data.looping else "Loop: off")
        self._buttons.append(self._loop_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # PROGRESS BAR + SCRUB
    # ─────────────────────────────────────────────────────────────────────────

    _PROGRESS_H = 6.0
    _PROGRESS_PAD = 8.0

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + self._PROGRESS_PAD,
            r.bottom() - self._PROGRESS_H - self._PROGRESS_PAD,
            r.width() - self._PROGRESS_PAD * 2,
            self._PROGRESS_H,
        )

    def _scrub_to(self, x: float) -> None:
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        self._player.setPosition(int(ratio * self._duration_ms))

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
        if event.button() == Qt.LeftButton and self._progress_rect().contains(event.pos()):
            self._scrub_to(event.pos().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._progress_rect().contains(event.pos()):
            self._scrub_to(event.pos().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
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
        painter.setFont(title_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        label = self.data.caption or self.data.title
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            label,
        )

        # Status line
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setOpacity(0.7)
        y = r.top() + self._body_top()

        if not self.data.source_path:
            status = "Double-click to browse for audio"
        elif self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos_s = self._position_ms // 1000
            dur_s = self._duration_ms // 1000
            status = f"Playing  {pos_s // 60}:{pos_s % 60:02d} / {dur_s // 60}:{dur_s % 60:02d}"
        elif self._duration_ms > 0:
            pos_s = self._position_ms // 1000
            dur_s = self._duration_ms // 1000
            status = f"Paused  {pos_s // 60}:{pos_s % 60:02d} / {dur_s // 60}:{dur_s % 60:02d}"
        else:
            status = "Ready"

        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            status,
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
            painter.setBrush(QColor(Theme.primaryBorder))
            painter.drawRoundedRect(fill_rect, 3, 3)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if hasattr(self, '_vol_anim') and self._vol_anim:
            self._vol_anim.stop()
        self._audio.setVolume(0.0)
        try:
            self._player.durationChanged.disconnect(self._on_duration)
            self._player.positionChanged.disconnect(self._on_position)
            self._player.mediaStatusChanged.disconnect(self._on_media_status)
        except RuntimeError:
            pass
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._player.stop)
        super()._prepare_for_removal()

    def to_dict(self) -> dict:
        self.data.playback_pos = self._position_ms
        self.data.volume = int(self._target_volume * 100)
        self.data.muted = self._audio.isMuted()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'AudioNode':
        return AudioNode(AudioNodeData.from_dict(d))
