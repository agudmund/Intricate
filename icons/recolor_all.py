#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recolor all generated node/group icons to the ivory text_primary color.
Preserves alpha channel, replaces all RGB values.
Run from Intricate root:  python icons/recolor_all.py
"""

from PIL import Image
import os

IVORY = (210, 209, 207)  # #d2d1cf — text_primary from settings.toml

ICONS = [
    "about_node",
    "warm_node",
    "bezier_node",
    "health_node",
    "perf_node",
    "claude_node",
    "claude_census",
    "claude_response",
    "visual_group",
    "health_group",
    "tools_group",
    "polaroid",
    "text_node",
    "tree_node",
    "log_node",
    "snip_node",
    "reset_node",
    "tint_node",
    "restore_node",
    "sequence_node",
    "value_node",
    "palette_node",
    "image_node",
    "vision_eye",
]

OUT = os.path.dirname(__file__)


def recolor(img, color):
    """Replace all RGB with color, keep alpha intact."""
    r, g, b = color
    data = img.convert("RGBA")
    pixels = data.load()
    w, h = data.size
    for y in range(h):
        for x in range(w):
            _, _, _, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (r, g, b, a)
    return data


for name in ICONS:
    png_path = os.path.join(OUT, f"{name}.png")
    ico_path = os.path.join(OUT, f"{name}.ico")

    if not os.path.exists(png_path):
        print(f"skip  {name} (no .png found)")
        continue

    src = Image.open(png_path).convert("RGBA")
    out = recolor(src, IVORY)
    out.save(png_path)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    out.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"done  {name}")

print("all done")
