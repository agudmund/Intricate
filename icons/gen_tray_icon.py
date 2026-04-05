#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate minimize-to-tray icon: downward arrow into a horizontal tray/shelf.
Warm cream on transparent, outer ring matching iconic.png.
"""
from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Downward arrow (chevron pointing down)
W = 26
# Arrow shaft
draw.line([(cx, cy - 300), (cx, cy + 150)], fill=C, width=W)
# Arrow head
draw.line([(cx - 200, cy - 50), (cx, cy + 150)], fill=C, width=W)
draw.line([(cx + 200, cy - 50), (cx, cy + 150)], fill=C, width=W)

# Tray / shelf line at bottom
draw.line([(cx - 320, cy + 320), (cx + 320, cy + 320)], fill=C, width=W)

# Downsample
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/tray_node.png')

sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/tray_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
print("Created icons/tray_node.png and icons/tray_node.ico")
