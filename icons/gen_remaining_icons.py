#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate icons for Bezier, Paint Performance, and Health nodes.
Run from the Intricate root:  python icons/gen_remaining_icons.py

Standard Intricate icon language:
  - Warm cream (225, 213, 198) on transparent, outer ring identical to iconic.png

Icons produced
--------------
  bezier_node.ico  — Bezier Node     (S-curve with two control-handle dots)
  perf_node.ico    — Paint Perf      (stopwatch / frame-loop dial)
  health_node.ico  — Health Node     (heartbeat line — system vitals)
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


# ── 1. Bezier Node — S-curve with control handles ───────────────────────────
#    The classic bezier illustration: smooth curve + two tangent lines
#    ending in small circles (control points).
img, draw = _base()

p0 = (cx - 380, cy + 200)
p1 = (cx - 120, cy - 360)
p2 = (cx + 120, cy + 360)
p3 = (cx + 380, cy - 200)

# The smooth curve itself
curve = bezier(p0, p1, p2, p3)
for i in range(len(curve) - 1):
    draw.line([curve[i], curve[i + 1]], fill=C, width=36)

# Tangent lines from endpoints to their control points
draw.line([p0, p1], fill=C, width=20)
draw.line([p3, p2], fill=C, width=20)

# Control-point dots
dot_r = 36
for pt in [p0, p1, p2, p3]:
    draw.ellipse(
        [pt[0] - dot_r, pt[1] - dot_r, pt[0] + dot_r, pt[1] + dot_r],
        fill=C,
    )

_save(img, 'bezier_node')


# ── 2. Paint Performance — stopwatch dial ───────────────────────────────────
#    Circle with a needle at ~2 o'clock and two tick marks.
#    Reads as timer / performance / frame loop measurement.
img, draw = _base()

# Inner dial circle
dial_r = 340
draw.ellipse(
    [cx - dial_r, cy - dial_r, cx + dial_r, cy + dial_r],
    outline=C, width=34,
)

# Needle pointing at roughly 2 o'clock (~60 degrees from 12)
needle_angle = math.radians(-60)  # from 12 o'clock, clockwise
needle_len = 260
nx = cx + int(math.sin(needle_angle) * needle_len)
ny = cy - int(math.cos(needle_angle) * needle_len)
draw.line([(cx, cy), (nx, ny)], fill=C, width=30)

# Small center hub
hub_r = 32
draw.ellipse(
    [cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
    fill=C,
)

# Tick marks at 12, 3, 6, 9 positions (outside-facing short lines)
tick_inner = dial_r - 60
tick_outer = dial_r - 10
for hour_angle in [0, 90, 180, 270]:
    a = math.radians(hour_angle)
    x0 = cx + int(math.sin(a) * tick_inner)
    y0 = cy - int(math.cos(a) * tick_inner)
    x1 = cx + int(math.sin(a) * tick_outer)
    y1 = cy - int(math.cos(a) * tick_outer)
    draw.line([(x0, y0), (x1, y1)], fill=C, width=24)

_save(img, 'perf_node')


# ── 3. Health Node — heartbeat pulse ────────────────────────────────────────
#    Classic ECG waveform — flat, spike up, dip down, flat.
#    Distinct from the health_group icon: no cross, just the raw pulse.
img, draw = _base()

stroke = 36
points = [
    (cx - 480, cy + 30),
    (cx - 220, cy + 30),
    (cx - 140, cy - 40),
    (cx - 50,  cy - 320),
    (cx + 50,  cy + 240),
    (cx + 140, cy - 60),
    (cx + 220, cy + 30),
    (cx + 480, cy + 30),
]

for i in range(len(points) - 1):
    draw.line([points[i], points[i + 1]], fill=C, width=stroke)

_save(img, 'health_node')

print('all done')
