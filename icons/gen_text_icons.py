#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate icons for the About Node and Warm Node.
Run from the Intricate root:  python icons/gen_text_icons.py

Standard Intricate icon language:
  - Warm cream (225, 213, 198) on transparent, outer ring identical to iconic.png
  - Minimal silhouette inside — functional form, strong clear shape

Icons produced
--------------
  about_node.ico  — About / Sticky Note  (small tilted rectangle — a tag / label)
  warm_node.ico   — Warm Node            (gentle flame — warmth and comfort)
"""

from PIL import Image, ImageDraw
import math, os

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

OUT = os.path.dirname(__file__)


def _base():
    img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - 800, cy - 800, cx + 800, cy + 800], outline=C, width=52)
    return img, draw


def _save(img, name):
    path_ico = os.path.join(OUT, f'{name}.ico')
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(os.path.join(OUT, f'{name}.png'))
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    out.save(path_ico, format='ICO', sizes=[(s, s) for s in sizes])
    print(f'done  {path_ico}')


# ── 1. About Node — tilted sticky note / label ──────────────────────────────
#    A small rounded rectangle, slightly tilted, with a fold corner.
#    Reads as a sticky note / tag at a glance.
img, draw = _base()

# Rounded rectangle body — slightly tilted via manual polygon
# Working area roughly cx +/- 350, cy +/- 280
tilt = 0.12  # radians — subtle tilt
cos_t, sin_t = math.cos(tilt), math.sin(tilt)

# Rectangle corners before tilt (centered at cx, cy+20)
hw, hh = 280, 220
oy = 20  # nudge down slightly from center
corners = [
    (-hw, -hh + oy), (hw, -hh + oy),
    (hw, hh + oy), (-hw, hh + oy),
]
# Apply tilt around center
rotated = [
    (cx + int(x * cos_t - y * sin_t), cy + int(x * sin_t + y * cos_t))
    for x, y in corners
]
# Draw the note outline
stroke = 36
for i in range(4):
    draw.line([rotated[i], rotated[(i + 1) % 4]], fill=C, width=stroke)

# Folded corner — small triangle at top-right
fold_size = 120
# Top-right corner is rotated[1], fold goes inward
tr = rotated[1]
# Direction along top edge (from right toward left)
dx_top = rotated[0][0] - rotated[1][0]
dy_top = rotated[0][1] - rotated[1][1]
top_len = math.hypot(dx_top, dy_top)
dx_top, dy_top = dx_top / top_len, dy_top / top_len
# Direction along right edge (from top toward bottom)
dx_right = rotated[2][0] - rotated[1][0]
dy_right = rotated[2][1] - rotated[1][1]
right_len = math.hypot(dx_right, dy_right)
dx_right, dy_right = dx_right / right_len, dy_right / right_len

fold_a = (int(tr[0] + dx_top * fold_size), int(tr[1] + dy_top * fold_size))
fold_b = (int(tr[0] + dx_right * fold_size), int(tr[1] + dy_right * fold_size))
draw.line([fold_a, fold_b], fill=C, width=stroke)

# Two text lines inside the note
line_y1 = cy - 20
line_y2 = cy + 80
line_x0 = cx - 160
line_x1a = cx + 180
line_x1b = cx + 60  # shorter second line
for ly, lx1 in [(line_y1, line_x1a), (line_y2, line_x1b)]:
    # Tilt the line endpoints
    for pt in [(line_x0 - cx, ly - cy), (lx1 - cx, ly - cy)]:
        pass
    x0r = cx + int((line_x0 - cx) * cos_t - (ly - cy) * sin_t)
    y0r = cy + int((line_x0 - cx) * sin_t + (ly - cy) * cos_t)
    x1r = cx + int((lx1 - cx) * cos_t - (ly - cy) * sin_t)
    y1r = cy + int((lx1 - cx) * sin_t + (ly - cy) * cos_t)
    draw.line([(x0r, y0r), (x1r, y1r)], fill=C, width=24)

_save(img, 'about_node')


# ── 2. Warm Node — gentle flame ─────────────────────────────────────────────
#    Smooth S-curve flame shape — warmth, comfort, a candle glow.
#    Built from bezier-approximated curves using line segments.
img, draw = _base()

def bezier(p0, p1, p2, p3, steps=60):
    """Cubic bezier curve as list of (x, y) integer points."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((int(x), int(y)))
    return pts

# Flame outline — two mirrored S-curves meeting at tip and base
# Left side: base-center sweeps left then curves up to the pointed tip
# Right side: mirror

base_y = cy + 300    # bottom of flame
tip_y  = cy - 380    # top point
base_x = cx          # center base

# Left curve
left_pts = bezier(
    (base_x,       base_y),       # start: center bottom
    (base_x - 300, base_y - 100), # control: sweep left
    (base_x - 220, tip_y + 300),  # control: curve inward
    (base_x,       tip_y),        # end: tip
)

# Right curve
right_pts = bezier(
    (base_x,       tip_y),        # start: tip
    (base_x + 220, tip_y + 300),  # control: curve inward
    (base_x + 300, base_y - 100), # control: sweep right
    (base_x,       base_y),       # end: center bottom
)

flame = left_pts + right_pts
for i in range(len(flame) - 1):
    draw.line([flame[i], flame[i + 1]], fill=C, width=36)

# Inner flicker — smaller teardrop inside, offset upward
inner_base_y = cy + 140
inner_tip_y  = cy - 160

inner_left = bezier(
    (base_x,       inner_base_y),
    (base_x - 120, inner_base_y - 60),
    (base_x - 100, inner_tip_y + 140),
    (base_x,       inner_tip_y),
)
inner_right = bezier(
    (base_x,       inner_tip_y),
    (base_x + 100, inner_tip_y + 140),
    (base_x + 120, inner_base_y - 60),
    (base_x,       inner_base_y),
)
inner = inner_left + inner_right
for i in range(len(inner) - 1):
    draw.line([inner[i], inner[i + 1]], fill=C, width=26)

_save(img, 'warm_node')

print('all done')
