#!/usr/bin/env python3
"""Generate mute_off and mute_on icons — speaker with/without strike-through."""
from PIL import Image, ImageDraw

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


def _draw_speaker(draw):
    """Draw the speaker body — a wedge shape pointing right."""
    # Speaker cone (rectangle + triangle flare)
    # Rectangle part (speaker back)
    bx, by = cx - 280, cy - 120
    draw.rectangle([bx, by, bx + 160, cy + 120], fill=C)
    # Triangle flare expanding to the left
    draw.polygon([
        (bx, by),
        (bx - 200, by - 160),
        (bx - 200, cy + 120 + 160),
        (bx, cy + 120),
    ], fill=C)


def _draw_sound_waves(draw):
    """Draw two arcs to the right of the speaker for active sound."""
    sw = 30
    # Inner arc
    draw.arc([cx - 10, cy - 180, cx + 280, cy + 180], start=-50, end=50, fill=C, width=sw)
    # Outer arc
    draw.arc([cx + 80, cy - 300, cx + 480, cy + 300], start=-50, end=50, fill=C, width=sw)


# ── Mute OFF (speaker with sound waves — audio is active) ────────────────
img_off = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d_off   = ImageDraw.Draw(img_off)
d_off.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)
_draw_speaker(d_off)
_draw_sound_waves(d_off)
_save(img_off, 'mute_off')

# ── Mute ON (speaker with diagonal strike) ───────────────────────────────
img_on = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d_on   = ImageDraw.Draw(img_on)
d_on.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)
_draw_speaker(d_on)
# Diagonal strike-through
d_on.line([(cx - 420, cy - 350), (cx + 350, cy + 350)], fill=C, width=44)
_save(img_on, 'mute_on')
