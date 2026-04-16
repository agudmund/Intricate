#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate FBX node icon: wireframe cube inside the standard outer ring."""

from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream
W  = 26                      # stroke width at 2048

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — consistent with all icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# ── Wireframe cube — isometric-ish projection ────────────────────────
# Front face (square, slightly left of centre)
s = 280  # half-size of cube face
ox, oy = -60, 20  # offset to leave room for depth lines
# Front face corners
fl = (cx + ox - s, cy + oy - s)  # front top-left
fr = (cx + ox + s, cy + oy - s)  # front top-right
bl = (cx + ox - s, cy + oy + s)  # front bottom-left
br = (cx + ox + s, cy + oy + s)  # front bottom-right

# Back face — offset up-right for depth
dx, dy = 200, -200
rl = (fl[0] + dx, fl[1] + dy)
rr = (fr[0] + dx, fr[1] + dy)
tl = (bl[0] + dx, bl[1] + dy)
tr = (br[0] + dx, br[1] + dy)

# Front face
draw.line([fl, fr], fill=C, width=W)
draw.line([fr, br], fill=C, width=W)
draw.line([br, bl], fill=C, width=W)
draw.line([bl, fl], fill=C, width=W)

# Back face
draw.line([rl, rr], fill=C, width=W)
draw.line([rr, tr], fill=C, width=W)
draw.line([tr, tl], fill=C, width=W)
draw.line([tl, rl], fill=C, width=W)

# Connecting edges (depth lines)
draw.line([fl, rl], fill=C, width=W)
draw.line([fr, rr], fill=C, width=W)
draw.line([bl, tl], fill=C, width=W)
draw.line([br, tr], fill=C, width=W)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('fbx_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('fbx_node.ico', format='ICO', sizes=[(s, s) for s in sizes])
print("Created fbx_node.png + fbx_node.ico")
