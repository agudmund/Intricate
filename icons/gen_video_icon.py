#!/usr/bin/env python3
"""Generate video_node icon — play triangle + film strip accents inside the standard ring."""
from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — matches all other icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Play triangle — centred, pointing right
tri_size = 380
# Shift right slightly to look visually centred (optical balance)
ox = 40
pts = [
    (cx - tri_size * 0.45 + ox, cy - tri_size * 0.55),
    (cx + tri_size * 0.55 + ox, cy),
    (cx - tri_size * 0.45 + ox, cy + tri_size * 0.55),
]
draw.polygon(pts, fill=C)

# Small film-strip sprocket holes — two columns flanking the triangle
hole_w, hole_h = 40, 50
gap = 110
for side in (-1, 1):
    hx = cx + side * 520
    for i in range(-2, 3):
        hy = cy + i * gap
        draw.rounded_rectangle(
            [hx - hole_w//2, hy - hole_h//2, hx + hole_w//2, hy + hole_h//2],
            radius=8, fill=C
        )

# Downsample
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/video_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/video_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
print("video_node.ico created")
