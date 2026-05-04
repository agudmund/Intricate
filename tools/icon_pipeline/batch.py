#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - batch.py shared icon-list iteration for batch utilities
-and they learnt to whisper to each other across the same canonical roster for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# The three batch utilities (recolor_all, solidify_all, rebuild_ico)
# all do the same thing structurally:
#
#   for name in ICONS:
#       open icons/{name}.png
#       transform_pixels(img)
#       save icons/{name}.png + multi-resolution .ico
#
# Before this module each of those three scripts had its own slightly-
# divergent ICONS list — `recolor_all` had 24 entries, `solidify_all`
# had 23, `rebuild_ico` had 23 — and the divergence was the actual drift
# the audit caught.  Centralising the list here means the three scripts
# now operate on the same roster, automatically.

from typing import Callable
from PIL import Image

from .save import save_png_and_ico
from .paths import ICONS_DIR

# The canonical roster of "icons you'd want to recolour / solidify /
# rebuild in bulk."  Family-1 line-art icons that share the same cream
# colour and are the most likely targets of a global pass.  Sticker
# and emoji extractions are NOT in this list — they have their own
# extract scripts that re-run from source when they need updating.
#
# Add a new line-art icon to this list when it's stable enough that
# you'd want it to participate in a global recolour or rebuild.
BATCH_TARGETS: list[str] = [
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


def run_over_icons(
    op: Callable[[Image.Image], Image.Image],
    *,
    names: list[str] | None = None,
    output_dir = None,
) -> None:
    """Iterate the canonical roster, apply ``op`` to each PNG, save back.

    ``op`` receives a freshly-opened RGBA ``PIL.Image`` and returns the
    transformed image.  Whatever it returns is saved over the original
    via ``save_png_and_ico`` (which rebuilds the .ico from the same
    pixel data, so PNG and ICO stay in sync).

    ``names`` defaults to ``BATCH_TARGETS``.  Override only if a script
    needs to operate on a non-canonical subset (rare).

    Skips silently with a printed line if a name's PNG is missing —
    no exception, no halt, so a single missing file can't take down a
    whole batch run.
    """
    targets = names if names is not None else BATCH_TARGETS
    out_dir = output_dir if output_dir is not None else ICONS_DIR

    for name in targets:
        png_path = out_dir / f"{name}.png"
        if not png_path.exists():
            print(f"skip  {name} (no .png at {png_path})")
            continue

        src = Image.open(png_path).convert("RGBA")
        result = op(src)
        save_png_and_ico(result, name, output_dir=out_dir)
        print(f"done  {name}")

    print("all done")
