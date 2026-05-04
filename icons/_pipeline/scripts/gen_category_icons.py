#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate category icons for Visual and Health sidebar groups.
Run from the Intricate root:  python icons/gen_category_icons.py

Standard Intricate icon language (updated — info_node.ico baseline):
  - Warm cream (225, 213, 198) on transparent
  - Thin outer ring (width=12 at 2048 → ~6 px at 1024)
  - Large central symbol filling most of the interior

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
RING_W = 12   # thin ring — matches info_node.ico baseline

# Script lives at icons/_pipeline/scripts/ now — go up 3 levels to repo
# root, then into icons/ for the output target.  Pre-2026-05-04 the
# script was directly in icons/ and OUT was just dirname(__file__).
OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "icons"))


def _base():
    img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - 800, cy - 800, cx + 800, cy + 800], outline=C, width=RING_W)
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
    out.save(path_ico, format='ICO', sizes=[(s, s) for s in sizes])
    print(f'done  {path_ico}')


# ── 1. Visual group — S-curve + palette dots ────────────────────────────────
#    A flowing bezier S-curve with three circles underneath suggesting
#    paint dabs / palette swatches. Art + drawing at a glance.  Scaled up
#    to fill the interior now that the outer ring is thin.
img, draw = _base()

curve = bezier(
    (cx - 520, cy + 140),
    (cx - 140, cy - 460),
    (cx + 140, cy + 460),
    (cx + 520, cy - 140),
)
stroke = 52
for i in range(len(curve) - 1):
    draw.line([curve[i], curve[i + 1]], fill=C, width=stroke)

# Three palette dots below the curve, proportionally scaled up
dot_y = cy + 420
dot_r = 60
for dx in [-220, 0, 220]:
    draw.ellipse(
        [cx + dx - dot_r, dot_y - dot_r, cx + dx + dot_r, dot_y + dot_r],
        fill=C,
    )

_save(img, 'visual_group')


# ── 2. Health group — heartbeat pulse line ───────────────────────────────────
#    Classic ECG/heartbeat waveform — flat, spike up, spike down, flat.
#    Reads immediately as vitals / monitoring / health.  Scaled up to
#    fill the interior.
img, draw = _base()

stroke = 52
# Heartbeat path: flat → rise → sharp peak → sharp valley → rise → flat.
# All extents held inside ~660 from center so the ring gets a clear halo.
points = [
    (cx - 640, cy + 30),
    (cx - 280, cy + 30),
    (cx - 170, cy - 100),
    (cx -  60, cy - 440),
    (cx +  60, cy + 320),
    (cx + 170, cy - 110),
    (cx + 280, cy + 30),
    (cx + 640, cy + 30),
]

for i in range(len(points) - 1):
    draw.line([points[i], points[i + 1]], fill=C, width=stroke)

# No medical-cross accent — the ECG waveform alone reads as health,
# and keeping the symbol as one connected stroke means the whole glyph
# can be re-tinted or alpha-modulated as a single spatial unit without
# awkward overlap in later projects.

_save(img, 'health_group')

print('all done')
