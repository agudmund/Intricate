#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - icons/gen_pingpong_icon.py ping-pong sticker placeholder
-the arrows turn around at both ends and walk back to where they came from
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Placeholder ping-pong sticker for VideoNode's tri-state loop button.
# Sticker family — flat fill + dark outline + transparent background, on the
# warm-cream palette used by the rest of Intricate's icons. Final design will
# be authored against the design brief; this is the stand-in.
#
# Run once as a standalone script:
#     python icons/gen_pingpong_icon.py

from PIL import Image, ImageDraw

S  = 2048           # render at 2× for smooth LANCZOS downsample
cx = cy = S // 2
CREAM = (225, 213, 198, 255)   # warm cream — matches the icon family palette

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — keep these values identical across all icons for visual
# consistency with the rest of the icon family.
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=CREAM, width=52)

# ── Symbol: a horizontal bar with arrowheads on both ends ────────────────
# The line itself sits at vertical centre. Arrowheads flare outward at each
# end so the read is "back and forth" — distinct from the loop icon's
# circular arrow and the off icon's single-direction return arrow.

bar_y         = cy
bar_half_len  = 460     # half-length of the central bar
bar_thickness = 50
arrow_w       = 200     # horizontal extent of each arrowhead
arrow_h       = 220     # vertical extent of each arrowhead

# Central bar
draw.rounded_rectangle(
    [cx - bar_half_len, bar_y - bar_thickness // 2,
     cx + bar_half_len, bar_y + bar_thickness // 2],
    radius=bar_thickness // 2,
    fill=CREAM,
)

# Left arrowhead (pointing left)
left_tip_x = cx - bar_half_len - arrow_w
left_tip_y = bar_y
left_top_x = cx - bar_half_len + 30   # slight overlap into the bar so no seam
left_top_y = bar_y - arrow_h // 2
left_bot_x = left_top_x
left_bot_y = bar_y + arrow_h // 2
draw.polygon(
    [(left_tip_x, left_tip_y), (left_top_x, left_top_y), (left_bot_x, left_bot_y)],
    fill=CREAM,
)

# Right arrowhead (pointing right)
right_tip_x = cx + bar_half_len + arrow_w
right_tip_y = bar_y
right_top_x = cx + bar_half_len - 30
right_top_y = bar_y - arrow_h // 2
right_bot_x = right_top_x
right_bot_y = bar_y + arrow_h // 2
draw.polygon(
    [(right_tip_x, right_tip_y), (right_top_x, right_top_y), (right_bot_x, right_bot_y)],
    fill=CREAM,
)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/pingpong_node.png')

# Multi-resolution ICO (Pillow downsamples internally)
out.save(
    'icons/pingpong_node.ico',
    format='ICO',
    sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]],
)

print('icons/pingpong_node.png + .ico written')
