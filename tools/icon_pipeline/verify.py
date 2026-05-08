#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - verify.py composite-on-dark companion writer
-and they learnt to whisper to each other across the same node-bg backdrop for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# The verification step.  Every sticker extraction writes a companion
# PNG composited onto the canonical node background — that's where a
# bad defringe reveals itself.  Visually check the _verify_*_dark.png
# before considering the extraction done.
#
# Verify PNGs land in Documents/Data/Icon Pipeline/ (the VERIFY_DIR
# constant in paths.py), not in icons/ — icons/ is reserved for
# production assets the running app references.  The verify composites
# are author-time audit artefacts and sit alongside the other runtime
# sidecars in Documents/Data/.

from pathlib import Path
from PIL import Image

from .canvas import OUTPUT_SIZE
from .paths import VERIFY_DIR

# Canonical Intricate node background — the colour every sticker has
# to look clean against.  If you see a white halo around a sticker on
# the running app, you missed the defringe step; the verify PNG would
# have caught it before the icon shipped.
NODE_BG = (45, 52, 54, 255)


def write_dark_verify(
    img: Image.Image,
    name: str,
    *,
    bg: tuple[int, int, int, int] = NODE_BG,
    output_dir: Path | None = None,
) -> Path:
    """Composite *img* over the node background colour and save as
    ``_verify_{name}_dark.png``.

    Returns the path to the written file for caller logging.

    Output defaults to Documents/Data/Icon Pipeline/.  The directory is
    created on demand so first-run on a fresh checkout still lands the
    file even if no other tooling has touched the location yet.
    """
    out_dir = output_dir if output_dir is not None else VERIFY_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), bg)
    canvas.paste(img, (0, 0), img)

    verify_path = out_dir / f"_verify_{name}_dark.png"
    canvas.save(verify_path)
    return verify_path
