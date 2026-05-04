#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate icons for the SessionNode.
Run from the Intricate root:  python icons/gen_session_icons.py

Icons produced
--------------
  session_node.ico    — Sidebar icon (document with stacked lines)
  session_import.ico  — Import button (arrow pointing down into a grid)
"""

from PIL import Image, ImageDraw
import os

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

# Script lives at tools/icon_pipeline/scripts/ now — go up 3 levels to
# repo root, then into icons/ for the output target.  Pre-2026-05-04
# the script was directly in icons/ and OUT was just dirname(__file__).
OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "icons"))


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


# ── 1. Session Node — document with stacked lines ──────────────────────────
#    Reads as "file / session / JSON document". Rounded rectangle body
#    with three horizontal lines (content) and a folded corner.
img, draw = _base()

stroke = 28

# Document body — rounded rectangle
doc_l = cx - 260
doc_r = cx + 260
doc_t = cy - 340
doc_b = cy + 340
corner_sz = 100
draw.rounded_rectangle(
    [doc_l, doc_t, doc_r, doc_b],
    radius=30, outline=C, width=stroke,
)

# Folded corner — triangle at top-right
fold_x = doc_r - corner_sz
fold_y = doc_t + corner_sz
draw.line([(fold_x, doc_t), (fold_x, fold_y)], fill=C, width=stroke)
draw.line([(fold_x, fold_y), (doc_r, fold_y)], fill=C, width=stroke)

# Three content lines inside the document
line_l = doc_l + 80
line_r = doc_r - 80
line_y_start = cy - 120
line_gap = 120
for i in range(3):
    y = line_y_start + i * line_gap
    # Vary line lengths for visual interest
    r = line_r if i == 0 else (line_r - 60 if i == 1 else line_r - 140)
    draw.line([(line_l, y), (r, y)], fill=C, width=24)

_save(img, 'session_node')


# ── 2. Session Import — downward arrow into a surface ───────────────────────
#    Arrow pointing down onto a flat line (the canvas). Reads as
#    "import / bring in / merge into". Sticker-style utility icon.
img, draw = _base()

stroke = 30

# Arrow shaft — vertical line
shaft_top = cy - 300
shaft_bot = cy + 100
draw.line([(cx, shaft_top), (cx, shaft_bot)], fill=C, width=stroke)

# Arrowhead — two diagonal lines
head_sz = 140
draw.line([(cx - head_sz, shaft_bot - head_sz), (cx, shaft_bot)], fill=C, width=stroke)
draw.line([(cx + head_sz, shaft_bot - head_sz), (cx, shaft_bot)], fill=C, width=stroke)

# Landing surface — horizontal line with small upturns at the ends
surface_y = cy + 240
surf_l = cx - 320
surf_r = cx + 320
upturn = 60
draw.line([(surf_l, surface_y - upturn), (surf_l, surface_y)], fill=C, width=stroke)
draw.line([(surf_l, surface_y), (surf_r, surface_y)], fill=C, width=stroke)
draw.line([(surf_r, surface_y), (surf_r, surface_y - upturn)], fill=C, width=stroke)

_save(img, 'session_import')


print('all done')
