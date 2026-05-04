#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the CodeNode sidebar icon — angle brackets with a forward slash.
The classic </> code symbol, clean and minimal.
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

w = 28   # stroke width

# Left angle bracket  <
draw.line([(cx - 420, cy), (cx - 180, cy - 240)], fill=C, width=w)
draw.line([(cx - 420, cy), (cx - 180, cy + 240)], fill=C, width=w)

# Right angle bracket  >
draw.line([(cx + 420, cy), (cx + 180, cy - 240)], fill=C, width=w)
draw.line([(cx + 420, cy), (cx + 180, cy + 240)], fill=C, width=w)

# Forward slash  /  in the centre
draw.line([(cx + 100, cy - 280), (cx - 100, cy + 280)], fill=C, width=w)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/code_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/code_node.ico', format='ICO', sizes=[(s, s) for s in sizes])

print("code_node.png + .ico written")
