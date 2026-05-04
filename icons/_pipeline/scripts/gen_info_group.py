#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the Info group sidebar icon — open book.
An open book representing documentation and reference material.
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

w = 26   # stroke width

# Spine — vertical centre line
draw.line([(cx, cy - 280), (cx, cy + 280)], fill=C, width=w)

# Left page — slight curve for open-book feel
draw.arc([cx - 420, cy - 280, cx, cy + 280], start=90, end=270, fill=C, width=w)
# Left page top and bottom edges
draw.line([(cx - 210, cy - 280), (cx, cy - 280)], fill=C, width=w)
draw.line([(cx - 210, cy + 280), (cx, cy + 280)], fill=C, width=w)

# Right page — mirror
draw.arc([cx, cy - 280, cx + 420, cy + 280], start=270, end=90, fill=C, width=w)
# Right page top and bottom edges
draw.line([(cx, cy - 280), (cx + 210, cy - 280)], fill=C, width=w)
draw.line([(cx, cy + 280), (cx + 210, cy + 280)], fill=C, width=w)

# Text lines on left page
for y_off in [-160, -80, 0, 80]:
    draw.line([(cx - 340, cy + y_off), (cx - 60, cy + y_off)], fill=C, width=14)

# Text lines on right page
for y_off in [-160, -80, 0, 80]:
    draw.line([(cx + 60, cy + y_off), (cx + 340, cy + y_off)], fill=C, width=14)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/info_group.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/info_group.ico', format='ICO', sizes=[(s, s) for s in sizes])

print("info_group.png + .ico written")
