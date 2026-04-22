#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/joy_buckets.py joy bucket counter store
-Detached one-line text store for the joy bucket count, ceremony-free for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path


# One line, one integer, at a predictable path. Lives outside version control
# (see .gitignore) — it's runtime state, not source. Chosen to be trivially
# editable by hand (or from a chat session) without touching settings.toml.
_STORE = Path(__file__).resolve().parent.parent / "Documents" / "data" / "joy_buckets.txt"


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
