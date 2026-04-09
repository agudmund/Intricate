#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process the spawn-nodes sticker icon.

Reads the reference image, makes the drop shadow 50% translucent
(dark pixels near the bottom/edges that sit below the white peel border),
trims transparent edges, pads to square, resamples to 1024x1024,
and outputs both .png and multi-resolution .ico.

The drop shadow is identified as dark, low-saturation pixels that are
already partially transparent or sit at the outer edge of the sticker.
The main sticker body (white border, purple fills, dark navy strokes)
stays fully opaque.
"""

from PIL import Image
import numpy as np
import os

SRC = os.path.join(os.path.dirname(__file__), "..", "Images",
                   "The new official icon reference point.png")
OUT = os.path.dirname(__file__)


def process():
    img = Image.open(SRC).convert("RGBA")
    arr = np.array(img, dtype=np.float64)

    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    # The drop shadow is dark (low brightness), low saturation, and already
    # has alpha < 255 OR is at the very edge of opaque regions.
    # Identify shadow pixels: dark, brownish/grey tones below the sticker body.
    brightness = (r + g + b) / 3.0
    max_rgb = np.maximum(np.maximum(r, g), b)
    min_rgb = np.minimum(np.minimum(r, g), b)
    saturation = np.where(max_rgb > 0, (max_rgb - min_rgb) / max_rgb, 0)

    # Shadow characteristics: dark (brightness < 120), low-ish saturation,
    # and not the dark navy stroke (which has higher saturation and brightness)
    # The navy strokes are ~(58, 43, 90) — dark but with notable saturation
    # The shadow is ~(100, 60, 60) — reddish-brown, low brightness
    is_dark = brightness < 130
    is_low_sat = saturation < 0.45
    is_reddish = r > b  # shadow has red > blue tint, navy strokes have blue > red
    is_shadow = is_dark & is_low_sat & is_reddish & (a > 0)

    # Make shadow pixels 50% of their current alpha
    new_a = a.copy()
    new_a[is_shadow] = a[is_shadow] * 0.5

    arr[:, :, 3] = new_a.astype(np.uint8)
    img = Image.fromarray(arr.astype(np.uint8))

    # Trim transparent edges
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Pad to square
    w, h = img.size
    side = max(w, h)
    pad = 20  # small breathing room
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(img, ((side + pad * 2 - w) // 2, (side + pad * 2 - h) // 2))

    # Resample to 1024
    out = canvas.resize((1024, 1024), Image.LANCZOS)
    out.save(os.path.join(OUT, "spawn_nodes.png"))
    print(f"done  {os.path.join(OUT, 'spawn_nodes.png')}")

    # Multi-resolution ICO
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
    ico_path = os.path.join(OUT, "spawn_nodes.ico")
    frames[0].save(
        ico_path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"done  {ico_path}")

    # Also save as the app icon (intricate.ico replacement)
    app_ico = os.path.join(OUT, "intricate_new.ico")
    frames[0].save(
        app_ico, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"done  {app_ico}")


if __name__ == "__main__":
    process()
