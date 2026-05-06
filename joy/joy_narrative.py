#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - joy/joy_narrative.py joy wake narrative log
-The accountant who watches the cat with words For Enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Why this exists
# ───────────────
# The third leg of the joy-wake integrity triangle:
#
#     1. Click event              (the human-side action)
#     2. [joy-wake] log line      (the runtime-side structured record)
#     3. Narrative entry          (THIS — the accountant taking notes)
#
# Each wake or suppression appends one sentence to a separate log file
# in a fixed authorial voice.  The phrases are machine-selected from
# templates defined here — they sound like first-person prose but the
# selection rule and template set form a stylistic signature.  A
# tamperer editing the log by hand cannot reproduce the cadence
# exactly without seeing both, and even with both, the voice is
# recognisable on inspection — drift in voice IS a tampering signal.
#
# Validation property:
#   - If the structured [joy-wake] log says WAKE happened at time T,
#     the narrative log should have a corresponding entry at time T
#     drawn from the wake-* templates.
#   - If the structured log says SUPPRESS via sleep_btn, the narrative
#     log should have an entry from suppress_sleep templates.
#   - Mismatch between the two logs → tampering of one of them.
#
# This is the human-language analogue of HMAC log signing: the
# integrity of each entry is bound to a stylistic key (the templates)
# that the tamperer doesn't naturally produce.
#
# Half-state note for next visitor
# ────────────────────────────────
# This module was previously delivered as a compiled .pyc to keep the
# templates out of plain sight (commit 34d52ac), but clean_pycache()
# wipes every *.pyc on exit, so the binary delivery silently
# disappeared between runs.  The .py source is back in place to get
# the ticker moving again — a janitor-compatible binary format
# (Rust .pyd, mirroring intricate_log) is the longer-term home if we
# want the templates obfuscated again.
#
# Original .py source: git show 753ffb6:utils/joy_narrative.py
# Call-site consolidation (introduced record_event): 34d52ac
# Graceful-absence import wrapper in main_window.py: fdfa1d8

import datetime as _dt
import time
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────
# TEMPLATES — the authorial voice
# ─────────────────────────────────────────────────────────────────────────
# Patterns to keep consistent (the stylistic signature):
#   - First-person observation, present-perfect or simple past
#   - Cat-as-subject framing (she stirred / she stayed / she lifted her head)
#   - Concrete sensory or motor detail (clicked, tapped, scrolled, drifted)
#   - Quiet register — "stirred", "lifted her head", "kept on dreaming"
#   - Em-dashes and commas for cadence; no exclamation marks; no all-caps
#   - One sentence per entry, complete with terminal punctuation
#
# Adding a new template: match the existing voice carefully.  The whole
# point of this file is that the templates form a recognisable
# signature — drift in voice IS a tampering signal.

NARRATIVES: dict[str, list[str]] = {
    # Wake — mouse press anywhere on her surface (canvas or any widget)
    "wake_press": [
        "Clicked something on her surface and she stirred awake to see what I was up to.",
        "A press landed and she lifted her head, curious about what had reached her.",
        "Mouse press on her territory — she came back from wherever she'd been resting.",
        "Touched something inside her and she opened her eyes, quiet attention restored.",
    ],

    # Wake — keyboard input
    "wake_key": [
        "Started typing and she perked up, ready for whatever was coming next.",
        "A keystroke arrived in her direction and she came back to listen.",
        "Tapped a key and she stirred, attentive again.",
        "Keys clicking near her, she lifted her head — that gentle acknowledgement.",
    ],

    # Wake — scroll wheel
    "wake_wheel": [
        "Scrolled across her viewport and she opened her eyes.",
        "Wheel turned in her direction and she returned from her rest.",
        "Scrolling reached her gently and she came back, no hurry.",
        "A scroll pass and she stirred, taking stock of the moment.",
    ],

    # Wake — cursor entered one of her widgets (gentle hover-attention)
    "wake_enter": [
        "The cursor drifted onto one of her widgets and she stirred.",
        "Hover landed on her — that gentle acknowledgement, then she lifted her head.",
        "Cursor crossed into her territory and she came quietly back awake.",
        "A pointer wandered onto her and she noticed without rushing.",
    ],

    # Suppress — sleep button itself was clicked, button handler will toggle
    "suppress_sleep": [
        "Pressed the sleep button on her and she stayed cozy, no false wake.",
        "Sleep toggle clicked — she remained tucked in, exactly as intended.",
        "Tapped the sleep button and the wake-on-touch knew to stay quiet.",
        "Sleep button reached her, the exemption held — she didn't stir.",
    ],

    # Suppress — curtains button (operator wants to roll up while she sleeps)
    "suppress_curtains": [
        "Rolled the curtains and she kept on dreaming, undisturbed.",
        "Curtains animation fired and she held her sleep through it.",
        "Operator pulled the curtains; she stayed exactly where she was.",
        "Curtain click slid past her — she didn't lift her head.",
    ],

    # Suppress — minimize-to-tray button
    "suppress_tray": [
        "Minimized to tray and she kept on dreaming.",
        "Tray button pressed; she remained quietly asleep.",
        "Minimize action passed her by while she rested.",
        "Sent her to the tray and she didn't notice — sleep held.",
    ],
}


# ─────────────────────────────────────────────────────────────────────────
# DISPATCH — raw event/exempt names → bucket key
# ─────────────────────────────────────────────────────────────────────────
# main_window.eventFilter() now passes the raw event-type name and the
# exempt-widget name (or None for actual wakes).  Bucket-mapping moved
# in here as part of the call-site consolidation (commit 34d52ac).

_WAKE_BUCKETS: dict[str, str] = {
    "mouse_press": "wake_press",
    "key_press":   "wake_key",
    "wheel":       "wake_wheel",
    "enter":       "wake_enter",
}

_SUPPRESS_BUCKETS: dict[str, str] = {
    "sleep_btn":    "suppress_sleep",
    "curtains_btn": "suppress_curtains",
    "tray_btn":     "suppress_tray",
}


# ─────────────────────────────────────────────────────────────────────────
# SELECTION + APPEND
# ─────────────────────────────────────────────────────────────────────────

def _select(bucket_key: str) -> Optional[str]:
    """Pick a narrative phrase from the given bucket.

    Selection is non-deterministic across calls — uses time_ns() so
    consecutive entries in the same bucket aren't identical.  The
    determinism that matters for validation is *which bucket* an event
    maps to, not which phrase within the bucket.  A tamperer can't
    predict the exact phrase, but neither can the operator — the
    validity check is "does this phrase belong to the templates of the
    bucket the structured log named?", not "is this phrase exactly
    bucket[N]?"
    """
    bucket = NARRATIVES.get(bucket_key)
    if not bucket:
        return None
    idx = time.time_ns() % len(bucket)
    return bucket[idx]


def record_event(path: Path, ev_name: str, exempt_name: Optional[str]) -> None:
    """Record one narrative entry for a wake or suppression event.

    *ev_name* is the raw event-type name from the eventFilter dispatch
    ("mouse_press", "key_press", "wheel", "enter", or str(QEvent.Type)
    for unknowns).
    *exempt_name* is None for actual wakes, otherwise the name of the
    exempt widget that suppressed the wake ("sleep_btn", "curtains_btn",
    "tray_btn", or another type-name for unknown widgets).

    Format on disk: ``YYYY-MM-DD HH:MM:SS — narrative sentence.``

    Failures are silent — this is an integrity-supporting log, not a
    contract.  A failed write leaves the rest of the app untouched.
    Unknown event/exempt names map to no bucket and produce no entry,
    so the structured log can still record an event that the narrative
    log skips (the absence is itself a signal: an unknown bucket).
    """
    if exempt_name is None:
        bucket_key = _WAKE_BUCKETS.get(ev_name)
    else:
        bucket_key = _SUPPRESS_BUCKETS.get(exempt_name)
    if bucket_key is None:
        return
    phrase = _select(bucket_key)
    if not phrase:
        return
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"{ts} — {phrase}\n")
    except OSError:
        # Caller can log at debug if it cares; integrity log is
        # supplementary, not load-bearing for app function.
        pass
