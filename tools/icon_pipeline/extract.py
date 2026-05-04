#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - extract.py shared steps for sticker / emoji extraction
-and they learnt to whisper to each other across the same defringe and trim for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Family-2 (emoji) and Family-3 (sticker) extraction share the same
# post-processing tail after their bespoke background-removal step.
# Three operations live here:
#
#   1. keep_largest_component  — kill stray dots (numpy + scipy.ndimage)
#   2. defringe_against_white  — reverse-composite white-matte contamination
#   3. trim_and_square         — bbox crop, square-pad, ready for resize
#
# Each one operates on a numpy float32 RGBA array (or a PIL image for
# trim_and_square) and is composable in any order.  The standard tail is
# (defringe → largest-component → trim_and_square → save_png_and_ico).

import numpy as np
from PIL import Image
from scipy.ndimage import label


def keep_largest_component(arr: np.ndarray) -> np.ndarray:
    """Keep only the largest connected component of non-zero alpha pixels.

    Modifies ``arr[:, :, 3]`` in place AND returns the array for chaining.
    Background pixels (alpha == 0) are unchanged.  Stray dots / artefacts
    that survived background removal but aren't connected to the main
    icon body are zeroed out.

    Input: float32 RGBA array, shape (H, W, 4).
    """
    a = arr[:, :, 3]
    alpha_mask = a > 0
    labeled, n = label(alpha_mask)
    if n > 0:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0   # ignore background label
        biggest = sizes.argmax()
        a[labeled != biggest] = 0
        arr[:, :, 3] = a
    return arr


def defringe_against_white(arr: np.ndarray, *, edge_threshold: int = 250) -> np.ndarray:
    """Reverse-composite white-matte contamination from semi-transparent edges.

    Anti-aliased edge pixels in a generated sticker carry baked-in white
    from the source matte.  Composite onto Intricate's dark canvas
    background and the baked-in white shows as a visible halo.  This
    function reverses the compositing math:

        observed = α · actual + (1 - α) · 255
        actual   = (observed - 255 · (1 - α)) / α

    Solid interior pixels (α >= edge_threshold, default 250) are left
    untouched — only the edge band needs correction.  Without this
    step, stickers look fine on white but visibly haloed on the canvas.

    Input: float32 RGBA array, shape (H, W, 4).  Modifies in place AND
    returns for chaining.
    """
    a = arr[:, :, 3]
    alpha_norm = np.clip(a / 255.0, 0.001, 1.0)
    semi_transparent = (a > 0) & (a < edge_threshold)
    for ch in range(3):
        original = arr[:, :, ch]
        decontaminated = (original - 255.0 * (1.0 - alpha_norm)) / alpha_norm
        arr[:, :, ch] = np.where(
            semi_transparent,
            np.clip(decontaminated, 0, 255),
            original,
        )
    return arr


def trim_and_square(img: Image.Image, *, padding_factor: float = 1.0) -> Image.Image:
    """Crop to bounding box, then pad to square with optional outer breath.

    ``padding_factor`` of 1.0 (default) gives a tight square fit — the
    output side equals max(width, height) of the trimmed bbox.  Values
    above 1.0 add outer transparent padding (e.g. 1.1 = 10 % outer
    breath, useful for stickers where the peel border benefits from
    a small canvas margin so the LANCZOS downsample doesn't clip the
    very edge pixels).

    Input: PIL RGBA image.  Returns a new image; does not modify input.
    """
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    cw, ch = img.size
    side = int(max(cw, ch) * padding_factor)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - cw) // 2, (side - ch) // 2))
    return square
