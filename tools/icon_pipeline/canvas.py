#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - canvas.py Family-1 canvas constructor
-and they learnt to whisper to each other across the same cream ring for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Family-1 (sidebar + toolbar line-art) entry point.  Every icon in
# this family starts with the same scaffolding:
#
#     S=2048 RGBA canvas, transparent background
#     cream colour (225, 213, 198, 255)
#     outer ring at ellipse([cx-800, cy-800, cx+800, cy+800], width=52)
#     symbol drawn inside the cx ± 550, cy ± 350 envelope
#
# The 2048 render-then-1024-LANCZOS-downsample is what produces smooth
# edges — Pillow's draw primitives don't anti-alias themselves, so
# drawing direct at 1024 yields visibly jagged strokes.

from PIL import Image, ImageDraw

# Public constants — used by callers and exposed at package level
CREAM       = (225, 213, 198, 255)   # warm cream — the family palette
CANVAS_SIZE = 2048                   # 2× render for LANCZOS downsample
OUTPUT_SIZE = 1024                   # final asset resolution

# Outer ring constants — kept identical across the entire family so the
# silhouette reads as one set rather than 30 unrelated drawings.
_RING_RADIUS = 800
_RING_WIDTH  = 52


def make_line_art_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw, int, int]:
    """Build the canonical Family-1 canvas with the outer ring already drawn.

    Returns ``(img, draw, cx, cy)`` so callers can immediately add their
    symbol via the returned ``draw`` handle.  The canvas is 2048×2048
    RGBA with a transparent background; downsample to 1024 via
    ``save_png_and_ico`` (or your own resize call) before saving.

    The cx/cy returned are convenience values matching the canvas centre
    — most symbol drawing is centre-relative, so having them as locals
    saves the caller a `S // 2` repeat at the top of every script.
    """
    img  = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx   = cy = CANVAS_SIZE // 2

    # Outer ring — identical across all sidebar / toolbar line-art icons.
    # Width 52 at 2048 → ~26 at 1024 → reads as a clean ~1px contour at
    # 24-32 px UI sizes.
    draw.ellipse(
        [cx - _RING_RADIUS, cy - _RING_RADIUS,
         cx + _RING_RADIUS, cy + _RING_RADIUS],
        outline=CREAM,
        width=_RING_WIDTH,
    )

    return img, draw, cx, cy
