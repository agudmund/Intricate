#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the Adobe group sidebar icon — solid silhouette of the Adobe 'A'
mark, stripped of its red fill so it lives in the warm cream palette the
rest of the sidebar uses.  No circular ring around it: brand-mark icons
(this one, Anthropic's 'Ai') are flat silhouettes, visually distinct from
the ringed line-art icons that represent internal categories.

Sits between the Info ring and the Anthropic 'Ai' so the bottom of the
sidebar reads as a letterform trio — A → i → Ai — clean down the strip.

Geometry: two trapezoidal legs meeting at a sharp peak, wide flat feet
at the bottom, an inverted triangular cutout in the centre where the
conventional A's crossbar would be.  Drawn as the outer silhouette then
masked with a triangle-shaped alpha subtraction to carve out the hole.
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream — sidebar family palette

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# ── Outer A silhouette ───────────────────────────────────────────────────
# Vertices traced clockwise from the peak.  The shape is a wedge/chevron
# that's narrow at the top and widens toward the bottom — each leg is
# effectively a trapezoid.

peak_y        = cy - 640     # sharp point at top
bottom_y      = cy + 580     # flat feet sit on this line
foot_outer    = 540          # how far each foot extends from centre
peak_offset   = 36           # peak is a sharp point, but give it a hair of
                             # width at the very top so the ICO rasterizer
                             # doesn't wash the apex out at 16 px
leg_inner_top = 26           # how wide each leg starts at the top
foot_inner    = 210          # inside edge of each foot at the bottom

# Outer outline, clockwise from peak
outer = [
    (cx - peak_offset,   peak_y),         # peak left
    (cx + peak_offset,   peak_y),         # peak right
    (cx + foot_outer,    bottom_y),       # right foot outer corner
    (cx + foot_inner,    bottom_y),       # right foot inner corner
    (cx - foot_inner,    bottom_y),       # left foot inner corner
    (cx - foot_outer,    bottom_y),       # left foot outer corner
]
draw.polygon(outer, fill=C)

# ── Triangular cutout (the signature negative space) ─────────────────────
# Build the cutout on a separate greyscale mask, then paste transparent
# pixels through that mask to subtract the triangle from the A's alpha.

cutout_apex_y   = cy - 150   # where the cutout triangle's peak sits
cutout_bottom_y = bottom_y   # cutout reaches the bottom edge of the feet
cutout_half_w   = 200        # half-width of the triangle at the bottom

cutout = [
    (cx,                    cutout_apex_y),       # apex pointing up
    (cx + cutout_half_w,    cutout_bottom_y),     # bottom-right
    (cx - cutout_half_w,    cutout_bottom_y),     # bottom-left
]

mask = Image.new('L', (S, S), 0)
ImageDraw.Draw(mask).polygon(cutout, fill=255)

# paste() with a mask treats mask luminance as "how much of the src to
# blend in".  Pasting a fully transparent image through a white-on-black
# mask zeroes the alpha wherever the mask is white — carving the hole.
hole = Image.new('RGBA', (S, S), (0, 0, 0, 0))
img.paste(hole, (0, 0), mask)

# ── Downsample + export ──────────────────────────────────────────────────
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/adobe_group.png')

sizes = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/adobe_group.ico', format='ICO', sizes=[(s, s) for s in sizes])

print("adobe_group.png + .ico written")
