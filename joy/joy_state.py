#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - joy/joy_state.py joy runtime persistence
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
# Sister to joy/joy_buckets.py — which holds the bucket count in a one-line
# .txt file with its own external-edit watcher. Same idea here, just two values
# instead of one, so JSON instead of plain text.

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QFileSystemWatcher, Signal


_STORE = Path(__file__).resolve().parent.parent / "Documents" / "Data" / "joy_state.json"


def _ensure_parent() -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    """Read the sidecar. Returns a dict with happy_secs (float), bar_value
    (int), last_active_at (ISO datetime string or None), grace_remaining
    (float or None), feed_wall_times (list of float wall-clock seconds),
    and last_feed_wall (float wall-clock seconds). Missing file or
    malformed contents return sensible defaults — a corrupted store
    should never crash startup, just reset the live pulse.

    last_active_at is the timestamp of the most recent save call, written
    on every save. On app launch, main_window reads this and compares it
    against the current time to compute elapsed-while-closed sleep decay
    on the bar. None on cold-start (no previous run) means no decay
    applied — bar starts at default.

    grace_remaining is the live in-grace countdown — None when the file
    has no override (the typical case; the running app keeps its own
    counter).  When Settlers writes a value here as an override, the
    file watcher fires and the running app picks up the new value live
    via _on_joy_state_external_change.  Intricate does not write this
    key on its own persists; it's strictly a Settlers→Intricate nudge
    channel, not a round-trip persistence value.

    feed_wall_times and last_feed_wall persist the per-feed cooldown
    and rolling-window cap across app restarts.  Stored in wall-clock
    (time.time()) terms so the elapsed-since-feed comparison stays
    honest across any downtime — the swallow gap is real biology, not
    session-local state, and "restart to bypass the cooldown" was a
    workaround that the joy_mood Phase 2 stomach-pouch mechanic
    requires us to close.  main_window converts these to current
    monotonic frame at boot, see _restore_feed_state_from_sidecar."""
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"happy_secs": 0.0, "bar_value": 100, "last_active_at": None,
                "grace_remaining": None,
                "feed_wall_times": [], "last_feed_wall": 0.0}
    raw_feed_times = data.get("feed_wall_times", [])
    feed_wall_times: list[float] = []
    if isinstance(raw_feed_times, list):
        for t in raw_feed_times:
            try:
                feed_wall_times.append(float(t))
            except (TypeError, ValueError):
                continue
    try:
        last_feed_wall = float(data.get("last_feed_wall", 0.0))
    except (TypeError, ValueError):
        last_feed_wall = 0.0
    return {
        "happy_secs":      float(data.get("happy_secs", 0.0)),
        "bar_value":       int(data.get("bar_value", 100)),
        "last_active_at":  data.get("last_active_at"),
        "grace_remaining": data.get("grace_remaining"),  # None if key absent
        "feed_wall_times": feed_wall_times,
        "last_feed_wall":  last_feed_wall,
    }


def save(
    happy_secs: float,
    bar_value: int,
    feed_wall_times: list[float] | None = None,
    last_feed_wall: float = 0.0,
) -> None:
    """Persist the current pulse + an ISO timestamp of the save moment.

    Called from the 30-second _persist_happy tick AND explicitly from
    closeEvent (so the at-close value is the actual at-close value, not
    whatever the last tick had). The timestamp drives sleep-decay on
    next launch — the app being closed is treated as the app being
    asleep, with the configured sleep_drain rate applied to the elapsed
    closed period to bring the bar down on wake.

    feed_wall_times / last_feed_wall persist the per-feed cooldown and
    rolling-window cap state across restarts (see load()'s docstring).
    Defaults are empty list / 0.0, matching a fresh start with no
    pending cooldown.  Caller (main_window._persist_happy) converts
    its in-memory monotonic timestamps to wall-clock at save time."""
    _ensure_parent()
    payload = {
        "happy_secs":      round(float(happy_secs), 1),
        "bar_value":       int(bar_value),
        "last_active_at":  datetime.now().isoformat(),
        "feed_wall_times": [round(float(t), 1) for t in (feed_wall_times or [])],
        "last_feed_wall":  round(float(last_feed_wall), 1),
    }
    # newline="\n" — keep LF on Windows so the file doesn't drift against
    # eol=lf if/when it joins the tracked sidecars in Documents/Data/.
    _STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


class JoyStateWatcher(QObject):
    """Watch the sidecar for external changes and emit the new state.

    "External" means any write not originating from the running Intricate
    instance — typically a Settlers slider drag, or a hand-edit from a
    chat session. The watcher lets the running app pick up such tweaks
    live instead of overwriting them on the next _persist_happy tick.

    Mirrors JoyBucketsWatcher in joy/joy_buckets.py — same defensive
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
