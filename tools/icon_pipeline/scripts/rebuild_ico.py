#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild every ICO in BATCH_TARGETS from its PNG source.

Run from project root:
    python tools/icon_pipeline/scripts/rebuild_ico.py

Why this script exists
──────────────────────
A line-art icon's .png is the source of truth.  The .ico is a derived
artefact, built from the .png at every batch run so the multi-resolution
layers stay synced with whatever the .png currently shows.  When the
.png is updated by hand (or by recolor_all / solidify_all), this script
is the one that re-emits the matching .ico.

Operates on the canonical BATCH_TARGETS roster from
tools/icon_pipeline/batch.py — the same list recolor_all and solidify_all
operate on, so the three scripts stay in lockstep.

Pre-toolkit version: ~50 lines with a hardcoded ICONS list that drifted
from its siblings.  After-toolkit version: ~10 lines, no list, no drift.
"""
import sys
from pathlib import Path

# Make tools.icon_pipeline importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from tools.icon_pipeline import run_over_icons


def _rebuild(img):
    """No pixel transformation — save_png_and_ico re-emits the .ico
    from the same .png pixels.  This op exists only because
    run_over_icons expects an op() callable."""
    return img


run_over_icons(_rebuild)
