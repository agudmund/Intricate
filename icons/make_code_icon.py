#!/usr/bin/env python3
"""Generate code_node icon — angle brackets < /> silhouette."""
from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

w = 26

# Left angle bracket  <
draw.line([(cx-280, cy-220), (cx-480, cy), (cx-280, cy+220)], fill=C, width=w, joint="curve")

# Right angle bracket  >
draw.line([(cx+280, cy-220), (cx+480, cy), (cx+280, cy+220)], fill=C, width=w, joint="curve")

# Forward slash  /
draw.line([(cx+120, cy-220), (cx-120, cy+220)], fill=C, width=w)

# Downsample
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/code_node.png')

sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/code_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
print("Done — code_node.png + .ico")
