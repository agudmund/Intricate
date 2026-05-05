#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/joy_narrative.py joy wake narrative log
-The accountant who watches the cat with words for enjoying
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
# Each wake or suppression appends a sentence to a separate log file in
# a fixed authorial voice.  The phrases are machine-selected from
# templates defined here — they sound like first-person prose but are
# actually a constrained pattern that I (the AI authoring this module)
# would write.  A tamperer editing the file by hand cannot reproduce
# the pattern exactly without seeing the templates and the selection
# rule, and even with both, the phrasing-cadence is mine specifically
# rather than generic — distinguishable on inspection.
#
# Validation property:
#   - If the structured [joy-wake] log says WAKE happened at time T,
#     the narrative log should have a corresponding entry at time T
#     drawn from the wake-* templates.
#   - If the structured log says SUPPRESS via sleep_btn, the narrative
#     log should have an entry from suppress_sleep templates.
#   - Mismatch between the two logs → tampering of one of them.
#   - A hand-edited narrative entry, even by the operator, is unlikely
#     to match the cadence of the templates and stands out immediately
#     to anyone who reads the log against the templates.
#
# This is the human-language analogue of HMAC log signing — the integrity
# of each entry is bound to a stylistic key (the templates) that the
# tamperer doesn't naturally produce.

from pathlib import Path


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
# point of this file is that the templates form a recognisable signature
# — drift in voice IS a tampering signal.

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
# SELECTION + APPEND
# ─────────────────────────────────────────────────────────────────────────

def select(bucket_key: str) -> str | None:
    """Pick a narrative phrase from the given bucket.

    Selection is non-deterministic across calls — uses time_ns() so
    consecutive entries in the same bucket aren't identical.  The
    determinism that matters for validation is *which bucket* an
    event maps to, not which phrase within the bucket.  A tamperer
    can't predict the exact phrase, but neither can the operator —
    the validity check is "does this phrase belong to the templates
    of the bucket the structured log named?"  not "is this phrase
    exactly bucket[N]?"
    """
    bucket = NARRATIVES.get(bucket_key)
    if not bucket:
        return None
    import time
    idx = time.time_ns() % len(bucket)
    return bucket[idx]


def append(path: Path, bucket_key: str) -> None:
    """Append one narrative entry to the log at *path*.

    Format: ``YYYY-MM-DD HH:MM:SS — narrative sentence.``

    Failures are silent — this is an integrity-supporting log, not a
    contract.  A failed write leaves the rest of the app untouched.
    """
    import datetime as _dt
    phrase = select(bucket_key)
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
