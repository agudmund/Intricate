#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - icons/make_premiere_bridge_icon.py Premiere bridge icon generator
-Pillow line-art recipe for the PremiereBridgeNode sidebar/button icon, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PIL import Image, ImageDraw

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# ── Outer ring (shared across icon family) ───────────────────────────────
draw.ellipse([cx - 800, cy - 800, cx + 800, cy + 800], outline=C, width=52)

# ── Suspension bridge motif ──────────────────────────────────────────────
# Two towers + draped cable + deck.  Reads as "bridge" at 16px and reminds
# you the packet is travelling from one shore (Intricate) to another
# (Premiere) over open water.
stroke = 28

# Tower geometry
tower_h_top    = cy - 340
tower_h_bottom = cy + 240
tower_w        = 36
tower_x_left   = cx - 420
tower_x_right  = cx + 420

# Left tower
draw.rectangle(
    [tower_x_left - tower_w, tower_h_top,
     tower_x_left + tower_w, tower_h_bottom],
    fill=C,
)
# Right tower
draw.rectangle(
    [tower_x_right - tower_w, tower_h_top,
     tower_x_right + tower_w, tower_h_bottom],
    fill=C,
)

# Tower caps — small pyramidal tops so the towers read as bridge pillars
cap = 70
draw.polygon(
    [(tower_x_left - tower_w - 10, tower_h_top),
     (tower_x_left + tower_w + 10, tower_h_top),
     (tower_x_left,                tower_h_top - cap)],
    fill=C,
)
draw.polygon(
    [(tower_x_right - tower_w - 10, tower_h_top),
     (tower_x_right + tower_w + 10, tower_h_top),
     (tower_x_right,                tower_h_top - cap)],
    fill=C,
)

# Deck — horizontal span between the towers
deck_y = cy + 200
draw.rectangle(
    [tower_x_left - 120,  deck_y - 14,
     tower_x_right + 120, deck_y + 14],
    fill=C,
)

# Suspension cable — parabolic curve between tower tops, dipping to deck
# Approximate parabola with a chord of line segments for crisp antialiasing.
cable_top_y     = tower_h_top - cap + 20      # anchored just under the caps
cable_bottom_y  = deck_y - 40                  # lowest sag above the deck
segments        = 48
xs = [tower_x_left + i * (tower_x_right - tower_x_left) / segments
      for i in range(segments + 1)]
def sag(x):
    # parabola: y = a*(x - cx)^2 + cable_bottom_y, anchored so endpoints sit
    # at (tower_x_left, cable_top_y) and (tower_x_right, cable_top_y).
    half = (tower_x_right - tower_x_left) / 2
    a = (cable_top_y - cable_bottom_y) / (half ** 2)
    return a * (x - cx) ** 2 + cable_bottom_y

ys = [sag(x) for x in xs]
for i in range(segments):
    draw.line([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])], fill=C, width=stroke)

# Vertical suspenders — short drops from the cable down to the deck.  These
# are the little tell-tale that *this is a bridge*, not just an arch.
suspenders = 9
for i in range(1, suspenders + 1):
    t = i / (suspenders + 1)
    x = tower_x_left + t * (tower_x_right - tower_x_left)
    y_cable = sag(x)
    draw.line([(x, y_cable), (x, deck_y - 14)], fill=C, width=12)

# ── Downsample + export ──────────────────────────────────────────────────
out = img.resize((1024, 1024), Image.LANCZOS)
out.save(r'C:\Users\thisg\Desktop\Intricate\icons\premiere_bridge.png')
out.save(
    r'C:\Users\thisg\Desktop\Intricate\icons\premiere_bridge.ico',
    format='ICO',
    sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]],
)
print("wrote premiere_bridge.png + premiere_bridge.ico")
