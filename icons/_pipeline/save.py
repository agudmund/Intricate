#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - save.py PNG + multi-resolution ICO output
-and they learnt to whisper to each other across the same output sizes for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# The universal output step.  Every icon — line-art, emoji, sticker —
# ends with this exact sequence: resize to 1024 LANCZOS, save PNG, save
# multi-resolution ICO with seven layer sizes.
#
# The seven sizes (16, 24, 32, 48, 64, 128, 256) are what Qt picks
# between for any given render target — a 16 px tray icon uses the 16 px
# layer, a 256 px menu icon uses the 256 px layer.  Single-resolution
# ICO yields blurry small renders; the layer set is load-bearing.

from pathlib import Path
from PIL import Image

from .canvas import OUTPUT_SIZE
from .paths import ICONS_DIR

# Multi-resolution ICO sizes — Qt picks the sharpest available layer
# for each render target, so shipping all seven means clean output at
# every UI size from tray (16) to menu (256).
DEFAULT_ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def save_png_and_ico(
    img: Image.Image,
    name: str,
    *,
    ico_sizes: list[int] | None = None,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Resize to 1024 LANCZOS, save ``{name}.png`` and ``{name}.ico``.

    Returns ``(png_path, ico_path)`` for caller logging or chaining.

    ``ico_sizes`` defaults to ``DEFAULT_ICO_SIZES`` (the canonical
    seven-layer set).  Override only for tray-icon-specific or
    similar narrow-target writes; the default is the right answer
    for every icon that lands on a `Theme.iconXxx` reference.

    ``output_dir`` defaults to the canonical ``./icons/`` directory.
    Override for staging / scratch outputs that shouldn't land in the
    real assets folder.

    The input image is resized in place — callers pass the 2048-px
    canvas, this function downsamples to 1024 with LANCZOS and saves
    both formats from the same downsampled source so the PNG and the
    256-px ICO layer are pixel-identical.
    """
    sizes = ico_sizes if ico_sizes is not None else DEFAULT_ICO_SIZES
    out_dir = output_dir if output_dir is not None else ICONS_DIR

    out = img.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)

    png_path = out_dir / f"{name}.png"
    ico_path = out_dir / f"{name}.ico"

    out.save(png_path)
    out.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])

    return png_path, ico_path
