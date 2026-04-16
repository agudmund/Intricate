#!/usr/bin/env python3
"""Generate screensnap icon — camera/viewfinder symbol for viewport capture."""
from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# Viewfinder / camera body — rounded rectangle
draw.rounded_rectangle(
    [cx-400, cy-280, cx+400, cy+300],
    radius=60, outline=C, width=28
)

# Lens — circle in center
draw.ellipse([cx-150, cy-130, cx+150, cy+150], outline=C, width=28)

# Small flash/viewfinder bump on top
draw.rounded_rectangle(
    [cx-100, cy-360, cx+100, cy-260],
    radius=20, outline=C, width=28
)

out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/screensnap_node.png')

sizes  = [16, 24, 32, 48, 64, 128, 256]
out.save('icons/screensnap_node.ico', format='ICO', sizes=[(s, s) for s in sizes])
print("saved icons/screensnap_node.ico")
