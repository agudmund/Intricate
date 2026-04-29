#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/joy_state.py joy runtime persistence
-Tiny JSON sidecar holding the live pulse — happy seconds + bar value for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Why this file exists separately from settings.toml: happy_secs and bar_value
# are runtime state that Intricate writes to itself every 30 seconds. Mixing
# that into settings.toml made the user's "grandMA control surface" fight with
# the app's own persistence loop — the settings.toml watcher would fire on
# Intricate's own writes, and runtime values appeared as user-tunable settings
# in The Settlers (which they aren't — exposing them as sliders would let the
# user "cheat" the joy gamification, the wrong shape).
#
# Sister to utils/joy_buckets.py — which holds the bucket count in a one-line
# .txt file with its own external-edit watcher. Same idea here, just two values
# instead of one, so JSON instead of plain text.

import json
from pathlib import Path

from PySide6.QtCore import QObject, QFileSystemWatcher, Signal


_STORE = Path(__file__).resolve().parent.parent / "Documents" / "Data" / "joy_state.json"


def _ensure_parent() -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    """Read the sidecar. Returns a dict with happy_secs (float) and bar_value
    (int). Missing file or malformed contents return sensible defaults — a
    corrupted store should never crash startup, just reset the live pulse."""
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"happy_secs": 0.0, "bar_value": 100}
    return {
        "happy_secs": float(data.get("happy_secs", 0.0)),
        "bar_value":  int(data.get("bar_value", 100)),
    }


def save(happy_secs: float, bar_value: int) -> None:
    """Persist the current pulse. Called from the 30-second _persist_happy tick."""
    _ensure_parent()
    payload = {
        "happy_secs": round(float(happy_secs), 1),
        "bar_value":  int(bar_value),
    }
    _STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class JoyStateWatcher(QObject):
    """Watch the sidecar for external changes and emit the new state.

    "External" means any write not originating from the running Intricate
    instance — typically a Settlers slider drag, or a hand-edit from a
    chat session. The watcher lets the running app pick up such tweaks
    live instead of overwriting them on the next _persist_happy tick.

    Mirrors JoyBucketsWatcher in utils/joy_buckets.py — same defensive
    re-add-on-change pattern (some editors save by delete+rename, which
    drops the watch handle), same idempotent ensure-watched flow.
    """
    changed = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._ensure_watched()
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _ensure_watched(self) -> None:
        if not _STORE.exists():
            save(0.0, 100)
        path = str(_STORE)
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    def _on_file_changed(self, _path: str) -> None:
        self._ensure_watched()
        self.changed.emit(load())
