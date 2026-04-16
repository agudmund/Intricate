#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild all .ico files from their .png sources with higher resolution layers.
Run from Intricate root:  python icons/rebuild_ico.py
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

    src = Image.open(png_path).convert("RGBA")

    # Upscale source to 512 if smaller, so the top ICO layer is crisp
    if src.width < 512:
        src = src.resize((512, 512), Image.LANCZOS)

    sizes = [16, 24, 32, 48, 64, 96, 128, 256]
    src.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"done  {name}")

print("all done")
