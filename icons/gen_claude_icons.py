#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the three Claude-family node icons.
Run from the Intricate root:  python icons/gen_claude_icons.py

All three share the standard Intricate icon language:
  - Warm cream (225, 213, 198) on transparent, outer ring identical to iconic.png
  - Inner mark: minimal tent shape abstracted from the Anthropic mark
  - Differentiated by a secondary symbol underneath the tent

Icons produced
--------------
  claude_node.ico      — Claude Node          (tent alone — clean, primary)
  claude_census.ico    — Token Census         (tent + three histogram bars)
  claude_response.ico  — Claude Response Node (tent + three text lines)
"""

from PIL import Image, ImageDraw
import os

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream — matches the icon family palette

OUT = os.path.join(os.path.dirname(__file__))


def _base():
    img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer ring — identical across all icons
    draw.ellipse([cx - 800, cy - 800, cx + 800, cy + 800], outline=C, width=52)
    return img, draw


def _tent(draw, centre_y, scale=1.0, stroke=40):
    """Two-leg tent — minimal abstraction of the Anthropic mark."""
    apex_x = cx
    apex_y = int(centre_y - 230 * scale)
    left_x = int(cx - 270 * scale)
    left_y = int(centre_y + 160 * scale)
    right_x = int(cx + 270 * scale)
    right_y = int(centre_y + 160 * scale)
    draw.line([(apex_x, apex_y), (left_x, left_y)], fill=C, width=stroke)
    draw.line([(apex_x, apex_y), (right_x, right_y)], fill=C, width=stroke)


def _save(img, name):
    path_png = os.path.join(OUT, f'{name}.png')
    path_ico = os.path.join(OUT, f'{name}.ico')
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(path_png)
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    out.save(path_ico, format='ICO', sizes=[(s, s) for s in sizes])
    print(f'done  {path_ico}')


# ── 1. Claude Node — tent only, full-centre ──────────────────────────────────
img, draw = _base()
_tent(draw, cy + 40)
_save(img, 'claude_node')


# ── 2. Claude Token Census — tent (upper) + histogram bars (lower) ───────────
#    Three vertical bars of ascending height suggest counting / metrics.
img, draw = _base()
_tent(draw, cy - 120, scale=0.78, stroke=36)

bar_base_y = cy + 360
bar_w      = 58
gap        = 120
heights    = [130, 200, 160]   # left, centre, right — slight variety
bar_xs     = [cx - gap, cx, cx + gap]
for bx, bh in zip(bar_xs, heights):
    draw.rectangle(
        [bx - bar_w // 2, bar_base_y - bh, bx + bar_w // 2, bar_base_y],
        fill=C,
    )
_save(img, 'claude_census')


# ── 3. Claude Response Node — tent (upper) + text lines (lower) ──────────────
#    Three horizontal lines suggest the response text flowing out below.
img, draw = _base()
_tent(draw, cy - 140, scale=0.75, stroke=36)

line_x0   = cx - 270
line_x1   = cx + 270
line_start_y = cy + 100
line_gap  = 100
for i in range(3):
    y = line_start_y + i * line_gap
    # Last line shorter — looks like a natural paragraph end
    x1 = line_x1 if i < 2 else cx + 80
    draw.line([(line_x0, y), (x1, y)], fill=C, width=34)
_save(img, 'claude_response')


# ── 4. Claude Vision Eye — tent (upper) + eye symbol (lower) ────────────────
#    An almond-shaped eye with a round pupil — represents the Vision API.
img, draw = _base()
_tent(draw, cy - 140, scale=0.75, stroke=36)

# Eye — almond shape: two arcs sharing left/right tips + circular pupil
eye_cy    = cy + 220
eye_hw    = 300     # half-width of almond (tips at cx ± hw)
peak_up   = 150     # how much upper lid curves above eye_cy
peak_dn   = 120     # how much lower lid curves below eye_cy
pupil_r   = 65      # pupil radius

# Upper lid — top half of an ellipse centred at eye_cy
draw.arc(
    [cx - eye_hw, eye_cy - peak_up, cx + eye_hw, eye_cy + peak_up],
    start=180, end=360,
    fill=C, width=32,
)
# Lower lid — bottom half of a slightly flatter ellipse, same centre
draw.arc(
    [cx - eye_hw, eye_cy - peak_dn, cx + eye_hw, eye_cy + peak_dn],
    start=0, end=180,
    fill=C, width=32,
)
# Pupil — filled circle
draw.ellipse(
    [cx - pupil_r, eye_cy - pupil_r, cx + pupil_r, eye_cy + pupil_r],
    fill=C,
)
_save(img, 'vision_eye')


print('all done')
