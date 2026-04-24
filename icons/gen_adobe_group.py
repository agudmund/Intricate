#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the Adobe group sidebar icon — an 'A' glyph inside the circular
family ring. Derived from the modern Adobe 2020+ identity (geometric A with
flat wide feet and a horizontal crossbar), stripped of its red fill so it
lives in the same warm cream line-art vocabulary as the rest of the sidebar.

Sits between the Info category and the Anthropic "Ai" glyph so the three
letterforms — A → i (info) → Ai (claude) — read cleanly from top to bottom.
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream — sidebar family palette

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical weight + diameter across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# ── The A glyph ──────────────────────────────────────────────────────────
#
# Two diagonals meet at a peak near the top of the safe zone, horizontal
# crossbar at about 35% up from the foot, flat wide feet at the bottom
# (the short horizontal stubs are what give the Adobe A its distinctive
# silhouette vs a plain triangle).

# Geometry anchors in 2048-space
peak_y       = cy - 360      # top of the A
foot_y       = cy + 360      # bottom of the legs
foot_spread  = 360           # horizontal distance from centre to each foot
foot_flare   = 70            # how far the feet extend beyond each leg's base
crossbar_y   = cy + 50       # crossbar sits in the lower third
stroke       = 56            # leg stroke width — chunky enough to read at 16px

# Left diagonal — foot-inner to peak
draw.line(
    [(cx - foot_spread, foot_y), (cx, peak_y)],
    fill=C, width=stroke,
)

# Right diagonal — mirror
draw.line(
    [(cx + foot_spread, foot_y), (cx, peak_y)],
    fill=C, width=stroke,
)

# Left flat foot — short stub extending outward from the leg's base
draw.line(
    [(cx - foot_spread - foot_flare, foot_y), (cx - foot_spread + foot_flare, foot_y)],
    fill=C, width=stroke,
)

# Right flat foot — mirror
draw.line(
    [(cx + foot_spread - foot_flare, foot_y), (cx + foot_spread + foot_flare, foot_y)],
    fill=C, width=stroke,
)

# Crossbar — trimmed slightly inside the legs so it doesn't visually
# overshoot when the diagonal stroke widths are accounted for
def _x_at_y(y_target: int) -> int:
    """Where the left diagonal crosses a given y — used to anchor the crossbar
    ends to the inside of the legs rather than floating mid-air."""
    # Linear interpolation along (cx - foot_spread, foot_y) → (cx, peak_y)
    t = (y_target - foot_y) / (peak_y - foot_y)
    return int(cx - foot_spread + t * foot_spread)

left_x  = _x_at_y(crossbar_y) + 20   # small inset so the crossbar joins cleanly
right_x = 2 * cx - left_x
draw.line(
    [(left_x, crossbar_y), (right_x, crossbar_y)],
    fill=C, width=stroke,
)

# ── Downsample + export ──────────────────────────────────────────────────
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/adobe_group.png')

sizes = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/adobe_group.ico', format='ICO', sizes=[(s, s) for s in sizes])

print("adobe_group.png + .ico written")
