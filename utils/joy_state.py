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
