#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - joy/joy_buckets.py joy bucket counter store
-Detached one-line text store for the joy bucket count, ceremony-free for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import QObject, QFileSystemWatcher, Signal


# One line, one integer, at a predictable path. Lives outside version control
# (see .gitignore) — it's runtime state, not source. Chosen to be trivially
# editable by hand (or from a chat session) without touching settings.toml.
_STORE = Path(__file__).resolve().parent.parent / "Documents" / "Data" / "joy_buckets.txt"


def _ensure_parent() -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)


def get_buckets() -> int:
    """Read the current bucket count. Returns 0 if file is missing or malformed —
    a malformed store shouldn't crash the app on startup, it should just reset
    the counter. The next bump will re-create it with a well-formed value."""
    try:
        return int(_STORE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def set_buckets(n: int) -> None:
    """Overwrite the bucket count with an explicit integer value."""
    _ensure_parent()
    _STORE.write_text(str(int(n)), encoding="utf-8")


def bump_buckets(delta: int = 1) -> int:
    """Add `delta` to the current count and return the new value. Convenience
    for the happy-accumulator path, which increments by one per earned bucket."""
    new_value = get_buckets() + int(delta)
    set_buckets(new_value)
    return new_value


class JoyBucketsWatcher(QObject):
    """Watch the backing store for external changes and emit the new value.

    External = any write to the file not originating from this running
    Intricate instance — most commonly a hand-edit from a chat session.
    The watcher lets the running app pick up those tweaks live instead of
    overwriting them on the next _persist_happy tick. Mirrors the pattern
    in utils/persistence/registry.py for settings.toml reloading.
    """
    changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._ensure_watched()
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _ensure_watched(self) -> None:
        # Some editors delete + rename on save, which drops the watch —
        # so we re-add the path defensively on every event, and create
        # the file if it doesn't yet exist so the watcher can latch.
        if not _STORE.exists():
            set_buckets(0)
        path = str(_STORE)
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    def _on_file_changed(self, _path: str) -> None:
        self._ensure_watched()
        self.changed.emit(get_buckets())
