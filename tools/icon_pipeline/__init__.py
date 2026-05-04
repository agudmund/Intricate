#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline — author-time toolkit (NOT runtime)
-and they learnt to whisper to each other across icon source and asset for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# What this is
# ────────────
# A small toolkit of pure-asset-transformation helpers used by the
# generation and extraction scripts in scripts/.  The runtime app does
# NOT import this — these functions only ever run when an icon is being
# authored, refreshed, or batch-processed.
#
# Why it exists
# ─────────────
# Before this toolkit, every gen_*.py and extract_*.py script copy-pasted
# the same scaffolding:
#   - 4-line Family-1 canvas + outer-ring setup
#   - 7-line largest-component cleanup
#   - 5-line defringe-against-white reverse-composite
#   - 3-line trim + square-pad
#   - 2-line multi-resolution ICO save
#   - 3-line verify-on-dark-bg companion PNG
# 47 scripts × overlapping copies of these blocks = 47 places drift can
# happen.  The three batch utilities (recolor_all, solidify_all,
# rebuild_ico) had three nearly-but-not-quite-identical hardcoded ICONS
# lists that proved exactly that drift.
#
# What's loaded here
# ──────────────────
# Public functions exposed at package level so callers can do
#     from tools.icon_pipeline import save_png_and_ico, defringe_against_white
# without hunting for the right submodule.

from .canvas import (
    make_line_art_canvas,
    CREAM,
    CANVAS_SIZE,
    OUTPUT_SIZE,
)
from .save import (
    save_png_and_ico,
    DEFAULT_ICO_SIZES,
)
from .extract import (
    keep_largest_component,
    defringe_against_white,
    trim_and_square,
)
from .verify import (
    write_dark_verify,
    NODE_BG,
)
from .batch import (
    run_over_icons,
    BATCH_TARGETS,
)
from .paths import (
    REPO_ROOT,
    ICONS_DIR,
    IMAGES_DIR,
)

__all__ = [
    # canvas
    "make_line_art_canvas", "CREAM", "CANVAS_SIZE", "OUTPUT_SIZE",
    # save
    "save_png_and_ico", "DEFAULT_ICO_SIZES",
    # extract
    "keep_largest_component", "defringe_against_white", "trim_and_square",
    # verify
    "write_dark_verify", "NODE_BG",
    # batch
    "run_over_icons", "BATCH_TARGETS",
    # paths
    "REPO_ROOT", "ICONS_DIR", "IMAGES_DIR",
]
