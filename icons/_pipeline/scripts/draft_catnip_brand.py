#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draft catnip brand mark — iteration 5.

Hearts doubled in size, shiny pink. Cream centre + rays.
"""

from PIL import Image, ImageDraw
import math, os

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)       # warm cream
HP = (230, 100, 140, 255)       # shiny pink for hearts
HL = (255, 150, 180, 255)       # pink highlight / shine

# Script lives at icons/_pipeline/scripts/ now — go up 3 levels to
# repo root, then into icons/ for the output target.  Pre-2026-05-04
# the script was directly in icons/ and OUT was just dirname(__file__).
OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "icons"))


def _save(img, name):
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(os.path.join(OUT, f'{name}.png'))
    print(f'done  {name}.png')


def _draw_heart_pink(draw, hx, hy, size):
    """Draw a shiny pink heart — base pink with a highlight lobe."""
    r = size
    # Base heart in pink
    draw.ellipse([hx - r, hy - r, hx, hy], fill=HP)
    draw.ellipse([hx, hy - r, hx + r, hy], fill=HP)
    draw.polygon([(hx - r, hy - r//4), (hx + r, hy - r//4),
                  (hx, hy + r)], fill=HP)
    # Shine highlight — smaller circle on the upper-left lobe
    sh_r = r // 3
    draw.ellipse([hx - r + sh_r//2, hy - r + sh_r//2,
                  hx - r + sh_r//2 + sh_r, hy - r + sh_r//2 + sh_r], fill=HL)


def _draw_rays(draw, origin_x, origin_y, base_angle=40):
    """3 radiating lines — generous spacing, thin→thick."""
    for i, offset in enumerate([-25, 0, 25]):
        angle = math.radians(base_angle + offset)
        inner_dist = 40
        outer_dist = 220 + i * 10
        w_start = 5
        w_end = 26 + i * 7

        x0 = origin_x + math.cos(angle) * inner_dist
        y0 = origin_y - math.sin(angle) * inner_dist
        x1 = origin_x + math.cos(angle) * outer_dist
        y1 = origin_y - math.sin(angle) * outer_dist

        perp = angle + math.pi / 2
        dx0 = math.cos(perp) * w_start / 2
        dy0 = math.sin(perp) * w_start / 2
        dx1 = math.cos(perp) * w_end / 2
        dy1 = math.sin(perp) * w_end / 2

        draw.polygon([
            (x0 - dx0, y0 + dy0), (x0 + dx0, y0 - dy0),
            (x1 + dx1, y1 - dy1), (x1 - dx1, y1 + dy1),
        ], fill=C)


# ═══════════════════════════════════════════════════════════════════════════
# K — Dot with big pink hearts
# ═══════════════════════════════════════════════════════════════════════════

img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

dot_cx = cx - 60
dot_cy = cy + 20
dot_r = 230

draw.ellipse([dot_cx - dot_r, dot_cy - dot_r,
              dot_cx + dot_r, dot_cy + dot_r], fill=C)

# Hearts 2x bigger (was 44, now 88), kissing the edge
_draw_heart_pink(draw, dot_cx - 100, dot_cy - dot_r - 30, 88)
_draw_heart_pink(draw, dot_cx + dot_r - 10, dot_cy + 80, 88)

_draw_rays(draw, dot_cx + dot_r - 40, dot_cy - dot_r + 40)

_save(img, 'catnip_draft_K_dot_pink')


# ═══════════════════════════════════════════════════════════════════════════
# L — Crescent with big pink hearts
# ═══════════════════════════════════════════════════════════════════════════

img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

cr_cx = cx - 50
cr_cy = cy + 10
r_out = 280
r_in = 220
shift = 130

draw.ellipse([cr_cx - r_out, cr_cy - r_out,
              cr_cx + r_out, cr_cy + r_out], fill=C)
draw.ellipse([cr_cx - r_in + shift, cr_cy - r_in - 30,
              cr_cx + r_in + shift, cr_cy + r_in - 30], fill=(0, 0, 0, 0))

# Hearts 2x bigger (was 42, now 84), snug at crescent tips
_draw_heart_pink(draw, cr_cx + 30, cr_cy - r_out + 10, 84)
_draw_heart_pink(draw, cr_cx + 80, cr_cy + r_out - 50, 84)

_draw_rays(draw, cr_cx + 140, cr_cy - 100)

_save(img, 'catnip_draft_L_crescent_pink')


print('\nall drafts done')
