#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the BloomNode sidebar icon — golden-angle spiral burst.
Particles scatter outward from a centre point in a sunflower pattern,
matching the node's original scatter algorithm.
"""

from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Golden-angle spiral dots radiating from centre
golden_angle = math.pi * (3 - math.sqrt(5))  # ~137.5°
num_dots = 55
max_r = 520
for i in range(1, num_dots + 1):
    angle = i * golden_angle
    # sqrt distribution gives even area density (sunflower pattern)
    r = max_r * math.sqrt(i / num_dots)
    dx = cx + r * math.cos(angle)
    dy = cy + r * math.sin(angle)
    # Dots get smaller toward the edge for depth
    dot_r = int(28 - 14 * (i / num_dots))
    draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=C)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/bloom_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/bloom_node.ico', format='ICO', sizes=[(s, s) for s in sizes])

print("bloom_node.png + .ico written")
