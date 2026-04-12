#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the NullNode sidebar icon — crosshair with centre dot.
Echoes the node's minimal transparent-anchor aesthetic:
Nuke's Dot, Houdini's Null SOP — just a position reference.
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Crosshair lines — gap in the centre for the dot
arm = 350       # half-length of each arm
gap = 80        # gap radius around centre dot
w   = 26        # stroke width

# Horizontal arms
draw.line([(cx - arm, cy), (cx - gap, cy)], fill=C, width=w)
draw.line([(cx + gap, cy), (cx + arm, cy)], fill=C, width=w)

# Vertical arms
draw.line([(cx, cy - arm), (cx, cy - gap)], fill=C, width=w)
draw.line([(cx, cy + gap), (cx, cy + arm)], fill=C, width=w)

# Centre dot
dot_r = 50
draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=C)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/null_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/null_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)

print("null_node.png + .ico written")
