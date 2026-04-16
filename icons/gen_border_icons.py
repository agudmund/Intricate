#!/usr/bin/env python3
"""Generate border_on / border_off icons for VideoNode border toggle."""
from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

def make_icon(name, draw_fn):
    img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer ring
    draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)
    draw_fn(draw)
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(f'icons/{name}.png')
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    out.save(f'icons/{name}.ico', format='ICO', sizes=[(s, s) for s in sizes])
    print(f"  saved icons/{name}.ico")

def border_on(draw):
    """A rounded rectangle with a visible thick border — border active."""
    r = 80
    draw.rounded_rectangle(
        [cx-350, cy-250, cx+350, cy+250],
        radius=r, outline=C, width=50
    )
    # Small inner rect to suggest content
    draw.rounded_rectangle(
        [cx-250, cy-150, cx+250, cy+150],
        radius=40, outline=C, width=20
    )

def border_off(draw):
    """A rounded rectangle with dashed/thin border — border inactive."""
    r = 80
    draw.rounded_rectangle(
        [cx-350, cy-250, cx+350, cy+250],
        radius=r, outline=C, width=20
    )
    # Diagonal slash through it
    draw.line([cx-200, cy-200, cx+200, cy+200], fill=C, width=24)

make_icon("border_on_node", border_on)
make_icon("border_off_node", border_off)
print("Done!")
