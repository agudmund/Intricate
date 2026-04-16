#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a full-color eye icon for the ImageNode vision-rename button.
Ivory white oval eye shape with retina colors (iris, pupil, highlight).
No background circle — the eye shape itself is the icon.
Run from Intricate root:  python icons/gen_vision_rename.py
"""

from PIL import Image, ImageDraw, ImageChops
import os

S   = 2048
cx  = cy = S // 2
OUT = os.path.dirname(__file__)

# ── Color palette ────────────────────────────────────────────────────
IVORY     = (210, 209, 207, 255)   # text_primary — the eye white / outer shape
IRIS_OUT  = (45,  90,  160, 255)   # outer iris — deep blue
IRIS_MID  = (70,  130, 200, 255)   # mid iris — steel blue
IRIS_IN   = (95,  155, 215, 255)   # inner iris ring — light blue
PUPIL     = (30,  25,  20,  255)   # near-black pupil
HIGHLIGHT = (255, 255, 255, 200)   # specular catch-light

img = Image.new('RGBA', (S, S), (0, 0, 0, 0))

# ── Oval eye shape — ivory fill, no background circle ────────────────
eye_cy   = cy
eye_hw   = 880      # half-extent — same in both axes for a circular shape
peak_up  = 880      # equal to eye_hw so the eye is round, not almond
peak_dn  = 880

# Build almond mask from intersection of upper/lower lid ellipse halves
upper_half = Image.new('L', (S, S), 0)
uh_draw = ImageDraw.Draw(upper_half)
uh_draw.ellipse(
    [cx - eye_hw, eye_cy - peak_up, cx + eye_hw, eye_cy + peak_up],
    fill=255,
)
uh_draw.rectangle([0, 0, S, eye_cy - 2], fill=0)  # keep bottom half (overlap 2px to kill seam)

lower_half = Image.new('L', (S, S), 0)
lh_draw = ImageDraw.Draw(lower_half)
lh_draw.ellipse(
    [cx - eye_hw, eye_cy - peak_dn, cx + eye_hw, eye_cy + peak_dn],
    fill=255,
)
lh_draw.rectangle([0, eye_cy + 2, S, S], fill=0)  # keep top half (overlap 2px to kill seam)

eye_mask = ImageChops.add(upper_half, lower_half)

# Fill the almond shape with ivory
ivory_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
ivory_flat  = Image.new('RGBA', (S, S), IVORY)
ivory_layer.paste(ivory_flat, mask=eye_mask)
img = Image.alpha_composite(img, ivory_layer)

# ── Iris — concentric rings for depth ────────────────────────────────
iris_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
ir_draw = ImageDraw.Draw(iris_layer)

iris_r = 520
ir_draw.ellipse(
    [cx - iris_r, eye_cy - iris_r, cx + iris_r, eye_cy + iris_r],
    fill=IRIS_OUT,
)
mid_r = 420
ir_draw.ellipse(
    [cx - mid_r, eye_cy - mid_r, cx + mid_r, eye_cy + mid_r],
    fill=IRIS_MID,
)
inner_r = 330
ir_draw.ellipse(
    [cx - inner_r, eye_cy - inner_r, cx + inner_r, eye_cy + inner_r],
    fill=IRIS_IN,
)
img = Image.alpha_composite(img, iris_layer)

# ── Pupil ────────────────────────────────────────────────────────────
pupil_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
pp_draw = ImageDraw.Draw(pupil_layer)
pupil_r = 210
pp_draw.ellipse(
    [cx - pupil_r, eye_cy - pupil_r, cx + pupil_r, eye_cy + pupil_r],
    fill=PUPIL,
)
img = Image.alpha_composite(img, pupil_layer)

# ── Specular highlight ───────────────────────────────────────────────
hl_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
hl_draw = ImageDraw.Draw(hl_layer)
hl_cx, hl_cy = cx + 100, eye_cy - 95
hl_r = 65
hl_draw.ellipse(
    [hl_cx - hl_r, hl_cy - hl_r, hl_cx + hl_r, hl_cy + hl_r],
    fill=HIGHLIGHT,
)
img = Image.alpha_composite(img, hl_layer)

# ── Save ─────────────────────────────────────────────────────────────
out = img.resize((1024, 1024), Image.LANCZOS)
out.save(os.path.join(OUT, 'vision_rename.png'))

sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save(os.path.join(OUT, 'vision_rename.ico'), format='ICO', sizes=[(s, s) for s in sizes])
print('done  vision_rename.png + vision_rename.ico')
