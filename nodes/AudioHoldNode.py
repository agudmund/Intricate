#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AudioHoldNode.py AudioHoldNode class
-Silence placeholder node with adjustable duration for merge sequencing, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.AudioNode import AudioNode
from data.AudioHoldNodeData import AudioHoldNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("audio_hold")

# Duration presets in seconds
_DURATIONS = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


class AudioHoldNode(AudioNode):
    """
    Silence placeholder — generates a silent WAV of configurable duration.

    Inherits from AudioNode so the MergeNode treats it identically.
    Click the duration label to cycle through presets.
    The silence file is auto-generated in a temp folder.
    """

    _has_depth_toggle = True

    def __init__(self, data: AudioHoldNodeData | None = None):
        if data is None:
            data = AudioHoldNodeData()
        super().__init__(data)
        self._generate_silence()

    # ─────────────────────────────────────────────────────────────────────────
    # SILENCE GENERATION
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_silence(self) -> None:
        """Generate a silent WAV file matching hold_seconds."""
        dur = self.data.hold_seconds
        self.data.caption = f"Silence {dur:.2f}s"
        self.data.title   = self.data.caption

        # Generate into a stable temp location keyed by uuid
        out_dir = Path(tempfile.gettempdir()) / "intricate_holds"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"hold_{self.data.uuid}.wav"

        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", f"{dur:.3f}",
                str(out_path),
            ], capture_output=True, check=True)
            self.load_from_path(str(out_path))
        except Exception as e:
            _log.warning(f"[AudioHoldNode] silence generation failed: {e}")

    def _cycle_duration(self) -> None:
        """Cycle to the next duration preset."""
        current = self.data.hold_seconds
        # Find next preset
        for d in _DURATIONS:
            if d > current + 0.001:
                self.data.hold_seconds = d
                self._generate_silence()
                return
        # Wrap around
        self.data.hold_seconds = _DURATIONS[0]
        self._generate_silence()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import EmojiButton
        # Call AudioNode's _build_buttons but skip the split button
        super()._build_buttons()

        # Duration cycle button
        self._dur_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u23f1",   # ⏱
            set_emoji=lambda _: self._cycle_duration(),
        )
        self._dur_btn.setToolTip("Cycle silence duration")
        self._buttons.append(self._dur_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION — disable file browser on double-click
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        """Hold nodes don't open a file browser — cycle duration instead."""
        from nodes.BaseNode import BaseNode
        if self._progress_rect().contains(event.pos()):
            event.accept()
            return
        self._cycle_duration()
        event.accept()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'AudioHoldNode':
        return AudioHoldNode(AudioHoldNodeData.from_dict(data))
