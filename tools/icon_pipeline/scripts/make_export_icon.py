#!/usr/bin/env python3
"""Generate export icon — an upward arrow emerging from a tray."""
from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Tray — open-top U shape
w = 24
draw.line([(cx-350, cy+50), (cx-350, cy+300), (cx+350, cy+300), (cx+350, cy+50)], fill=C, width=w, joint="curve")

# Upward arrow shaft
draw.line([(cx, cy+180), (cx, cy-280)], fill=C, width=w)

# Arrow head
draw.line([(cx-160, cy-120), (cx, cy-280), (cx+160, cy-120)], fill=C, width=w, joint="curve")

# Downsample
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/export_node.png')

sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/export_node.ico', format='ICO', sizes=[(s, s) for s in sizes])
print("Done — export_node.png + .ico")
