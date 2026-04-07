#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate sleep/moon icon for the joy sleep button."""

from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — consistent with all icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Crescent moon — circle with a masking circle offset to the right
# Draw main moon circle
moon_r = 340
moon_cx, moon_cy = cx - 40, cy
# Create a mask approach: draw filled circle, then erase with offset circle
moon_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
moon_draw = ImageDraw.Draw(moon_layer)
moon_draw.ellipse(
    [moon_cx - moon_r, moon_cy - moon_r, moon_cx + moon_r, moon_cy + moon_r],
    fill=C
)
# Erase a chunk to form crescent — offset circle to upper-right
cut_r = 280
cut_cx, cut_cy = moon_cx + 200, moon_cy - 60
moon_draw.ellipse(
    [cut_cx - cut_r, cut_cy - cut_r, cut_cx + cut_r, cut_cy + cut_r],
    fill=(0, 0, 0, 0)
)
img = Image.alpha_composite(img, moon_layer)

# Three small stars (tiny filled circles) scattered around
stars = [(cx + 280, cy - 280, 28), (cx + 380, cy - 120, 20), (cx + 200, cy - 400, 22)]
draw2 = ImageDraw.Draw(img)
for sx, sy, sr in stars:
    draw2.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=C)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('sleep_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'sleep_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
print("Created sleep_node.png + sleep_node.ico")
