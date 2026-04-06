#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/audio.py AudioFeedback
-Gentle audio feedback for UI interactions, global mute control for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from pathlib import Path

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtMultimedia import QSoundEffect

import pretty_widgets.utils.settings as settings
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("audio")


def _audio_dir() -> Path:
    """Resolve the audio folder — handles both dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys.executable).parent / "audio"
    return Path(__file__).resolve().parent.parent / "audio"


class AudioFeedback:
    """
    Singleton-ish manager for UI sound effects.

    Lazy-loads the chime WAV on first play. Respects the global mute
    state persisted in settings.toml [ui] muted.

    Usage::

        from utils.audio import audio
        audio.play_chime()
        audio.set_muted(True)
    """

    def __init__(self):
        self._chime: QSoundEffect | None = None
        self._muted = bool(settings.get("ui", "muted", False))

    def _get_chime(self) -> QSoundEffect | None:
        if self._chime is not None:
            return self._chime

        chime_path = _audio_dir() / "new_node_chime.wav"
        if not chime_path.exists():
            _log.warning(f"[audio] chime not found at {chime_path}")
            return None

        self._chime = QSoundEffect()
        self._chime.setSource(QUrl.fromLocalFile(str(chime_path)))
        self._chime.setVolume(0.6)
        self._chime.setLoopCount(1)

        if not self._chime.source().isValid():
            _log.warning("[audio] chime source invalid — disabling")
            self._chime = None

        return self._chime

    _FADE_STEPS    = 10
    _FADE_MS       = 300   # total fade-in duration
    _TARGET_VOLUME = 0.6

    def play_chime(self) -> None:
        """Play the node-creation chime with a gentle fade-in, unless globally muted."""
        if self._muted:
            return
        chime = self._get_chime()
        if chime:
            chime.setVolume(0.0)
            chime.play()
            self._fade_step = 0
            interval = self._FADE_MS // self._FADE_STEPS
            self._fade_timer = QTimer()
            self._fade_timer.setInterval(interval)
            self._fade_timer.timeout.connect(self._tick_fade)
            self._fade_timer.start()

    def _tick_fade(self) -> None:
        self._fade_step += 1
        progress = self._fade_step / self._FADE_STEPS
        if self._chime:
            self._chime.setVolume(self._TARGET_VOLUME * progress)
        if self._fade_step >= self._FADE_STEPS:
            self._fade_timer.stop()

    def is_muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        settings.set_value("ui", "muted", muted)


# Module-level singleton — import and use directly
audio = AudioFeedback()
