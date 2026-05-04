#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Solidify every line-art icon in BATCH_TARGETS — any pixel with alpha > 0
gets alpha = 255.  Background stays transparent.

Run from project root:
    python icons/_pipeline/scripts/solidify_all.py

Why this script exists
──────────────────────
LANCZOS downsample produces semi-transparent edge pixels by design —
that's how the smooth anti-aliasing happens.  But for SOLID line-art
icons (cream-on-transparent ring designs) the semi-transparent edges
read as muddy on dark backgrounds.  Solidify forces alpha → 255
everywhere a pixel exists, giving a hard edge that reads cleanly
against any backdrop.

Sticker icons (Family 3) should NOT be solidified — they rely on
the semi-transparent edge for the white peel border to feather
correctly.  BATCH_TARGETS contains line-art icons only; check before
adding new entries.

Operates on the canonical BATCH_TARGETS roster from
icons/_pipeline/batch.py — keeps in lockstep with rebuild_ico and
recolor_all.

Pre-toolkit version: ~63 lines, hardcoded ICONS list.  After-toolkit
version: ~15 lines.
"""
import sys
from pathlib import Path

# Make icons._pipeline importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from icons._pipeline import run_over_icons


def _solidify(img):
    """Force alpha to 255 wherever it's already > 0; leave fully-
    transparent pixels alone."""
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (r, g, b, 255)
    return img


run_over_icons(_solidify)
