#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate category icons for Visual and Health sidebar groups.
Run from the Intricate root:  python icons/gen_category_icons.py

Standard Intricate icon language:
  - Warm cream (225, 213, 198) on transparent, outer ring identical to iconic.png

Icons produced
--------------
  visual_group.ico  — Visual category (bezier curve + palette dot — art/drawing)
  health_group.ico  — Health category (heartbeat pulse line — monitoring/vitals)
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


def bezier(p0, p1, p2, p3, steps=80):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
        pts.append((int(x), int(y)))
    return pts


def _save(img, name):
    path_ico = os.path.join(OUT, f'{name}.ico')
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(os.path.join(OUT, f'{name}.png'))
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(
        path_ico, format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f'done  {path_ico}')


# ── 1. Visual group — S-curve + small palette dots ──────────────────────────
#    A flowing bezier S-curve with three small circles underneath
#    suggesting paint dabs / palette swatches. Art + drawing at a glance.
img, draw = _base()

curve = bezier(
    (cx - 400, cy + 100),
    (cx - 100, cy - 350),
    (cx + 100, cy + 350),
    (cx + 400, cy - 100),
)
for i in range(len(curve) - 1):
    draw.line([curve[i], curve[i + 1]], fill=C, width=36)

# Three palette dots below the curve
dot_y = cy + 280
dot_r = 44
for dx in [-160, 0, 160]:
    draw.ellipse(
        [cx + dx - dot_r, dot_y - dot_r, cx + dx + dot_r, dot_y + dot_r],
        fill=C,
    )

_save(img, 'visual_group')


# ── 2. Health group — heartbeat pulse line ───────────────────────────────────
#    Classic ECG/heartbeat waveform — flat, spike up, spike down, flat.
#    Reads immediately as vitals / monitoring / health.
img, draw = _base()

stroke = 36
# Heartbeat path: flat → rise → sharp peak → sharp valley → rise → flat
points = [
    (cx - 500, cy + 20),   # start flat
    (cx - 200, cy + 20),   # still flat
    (cx - 120, cy - 60),   # gentle rise
    (cx - 40,  cy - 340),  # sharp peak up
    (cx + 40,  cy + 260),  # sharp valley down
    (cx + 120, cy - 80),   # recovery rise
    (cx + 200, cy + 20),   # back to baseline
    (cx + 500, cy + 20),   # flat out
]

for i in range(len(points) - 1):
    draw.line([points[i], points[i + 1]], fill=C, width=stroke)

# Small cross below the pulse — medical/health accent
cross_cy = cy + 260
cross_cx = cx
arm = 70
cross_w = 28
draw.line([(cross_cx - arm, cross_cy), (cross_cx + arm, cross_cy)], fill=C, width=cross_w)
draw.line([(cross_cx, cross_cy - arm), (cross_cx, cross_cy + arm)], fill=C, width=cross_w)

_save(img, 'health_group')

print('all done')
