#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recolour every line-art icon in BATCH_TARGETS to ivory text-primary.

Preserves the alpha channel; replaces all RGB values where alpha > 0.

Run from project root:
    python icons/_pipeline/scripts/recolor_all.py

Why this script exists
──────────────────────
The cream colour `(225, 213, 198, 255)` was the original family palette;
ivory `#d2d1cf` (the current `text_primary` value in settings.toml) is
the runtime-cascaded chrome colour.  This script aligns the file
pixels with the runtime cascade so a fresh export matches what the
app actually paints.

Operates on the canonical BATCH_TARGETS roster from
icons/_pipeline/batch.py — keeps in lockstep with rebuild_ico and
solidify_all.

Pre-toolkit version: ~75 lines, hardcoded ICONS list, hand-rolled
ICO save.  After-toolkit version: ~25 lines, no list duplication.
"""
import sys
from pathlib import Path

# Make icons._pipeline importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from icons._pipeline import run_over_icons

IVORY = (210, 209, 207)   # #d2d1cf — text_primary from settings.toml


def _recolour(img):
    """Replace all RGB with IVORY; preserve alpha channel intact.

    Pixel-loop implementation kept (not numpy-vectorised) because at
    1024×1024 it's well under a second and the readability wins.  If
    a future canvas size grows past 4k this becomes worth a numpy pass.
    """
    pixels = img.load()
    w, h = img.size
    r, g, b = IVORY
    for y in range(h):
        for x in range(w):
            _, _, _, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (r, g, b, a)
    return img


run_over_icons(_recolour)
