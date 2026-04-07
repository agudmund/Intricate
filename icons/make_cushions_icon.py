#!/usr/bin/env python3
"""Generate cushions_node icon — a soft pillow/cushion silhouette."""
from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — consistent across all icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Cushion shape — a rounded rectangle with corner tufts
# Main cushion body
draw.rounded_rectangle(
    [cx-420, cy-280, cx+420, cy+280],
    radius=120,
    outline=C, width=28,
)

# Corner tufts — small circles at each corner to give that cushion look
tuft_r = 45
corners = [
    (cx-340, cy-200),
    (cx+340, cy-200),
    (cx-340, cy+200),
    (cx+340, cy+200),
]
for tx, ty in corners:
    draw.ellipse(
        [tx - tuft_r, ty - tuft_r, tx + tuft_r, ty + tuft_r],
        outline=C, width=22,
    )

# Cross-stitch lines connecting tufts (the classic cushion indentation)
draw.line([(cx-340, cy-200), (cx+340, cy+200)], fill=C, width=20)
draw.line([(cx+340, cy-200), (cx-340, cy+200)], fill=C, width=20)

# Downsample to 1024
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/cushions_node.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/cushions_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
print("Done — cushions_node.png + .ico")
