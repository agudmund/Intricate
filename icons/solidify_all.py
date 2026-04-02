#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make all icon shapes fully opaque — any pixel with alpha > 0 gets alpha = 255.
Background stays transparent. Run from Intricate root:  python icons/solidify_all.py
"""

from PIL import Image
import os

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
    "images_group",
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
]

OUT = os.path.dirname(__file__)

for name in ICONS:
    png_path = os.path.join(OUT, f"{name}.png")
    ico_path = os.path.join(OUT, f"{name}.ico")

    if not os.path.exists(png_path):
        print(f"skip  {name}")
        continue

    img = Image.open(png_path).convert("RGBA")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (r, g, b, 255)

    img.save(png_path)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"done  {name}")

print("all done")
