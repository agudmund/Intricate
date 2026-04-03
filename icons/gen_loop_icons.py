#!/usr/bin/env python3
"""Generate loop_off and loop_on icons — circular arrows for repeat/loop."""
from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

def _save(img, name):
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(f'icons/{name}.png')
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(
        f'icons/{name}.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:]
    )
    print(f"{name}.ico created")


def _draw_loop_arrows(draw):
    """Draw two circular arrows forming a loop symbol."""
    r = 300          # radius of the loop circle
    sw = 30          # stroke width
    arrow_sz = 80    # arrowhead size

    # Top arc (right half) — from ~200° to ~350°
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=200, end=350, fill=C, width=sw)
    # Bottom arc (left half) — from ~20° to ~170°
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=20, end=170, fill=C, width=sw)

    # Arrowhead at end of top arc (~350° = top-right)
    ax = cx + r * math.cos(math.radians(-10))
    ay = cy + r * math.sin(math.radians(-10))
    draw.polygon([
        (ax, ay),
        (ax - arrow_sz, ay - arrow_sz * 0.8),
        (ax + arrow_sz * 0.3, ay - arrow_sz * 0.6),
    ], fill=C)

    # Arrowhead at end of bottom arc (~170° = bottom-left)
    bx = cx + r * math.cos(math.radians(170))
    by = cy + r * math.sin(math.radians(170))
    draw.polygon([
        (bx, by),
        (bx + arrow_sz, by + arrow_sz * 0.8),
        (bx - arrow_sz * 0.3, by + arrow_sz * 0.6),
    ], fill=C)


# ── Loop OFF (loop arrows, will appear muted via fallback_color) ─────────
img_off = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d_off   = ImageDraw.Draw(img_off)
d_off.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)
_draw_loop_arrows(d_off)
_save(img_off, 'loop_off')

# ── Loop ON (same arrows — tinted green by Theme at runtime) ─────────────
img_on = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d_on   = ImageDraw.Draw(img_on)
d_on.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)
_draw_loop_arrows(d_on)
# Add a small "1" or infinity hint in the centre to distinguish on vs off
# Draw a small infinity symbol (lemniscate) in the centre
inf_w, inf_h = 140, 80
d_on.arc([cx - inf_w - 10, cy - inf_h, cx + 10, cy + inf_h],
         start=40, end=320, fill=C, width=24)
d_on.arc([cx - 10, cy - inf_h, cx + inf_w + 10, cy + inf_h],
         start=220, end=500, fill=C, width=24)
_save(img_on, 'loop_on')
