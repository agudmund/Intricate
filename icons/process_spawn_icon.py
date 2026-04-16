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

    # ── Helper: trim, pad, resample to 1024 ─────────────────────────────────
    def _to_1024(src, name):
        bbox = src.getbbox()
        cropped = src.crop(bbox) if bbox else src
        cw, ch = cropped.size
        side = max(cw, ch)
        _canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
        _canvas.paste(cropped, ((side + pad * 2 - cw) // 2, (side + pad * 2 - ch) // 2))
        result = _canvas.resize((1024, 1024), Image.LANCZOS)
        result.save(os.path.join(OUT, name))
        print(f"done  {name}")
        return result

    out = _to_1024(img, "spawn_nodes.png")

    # Multi-resolution ICO
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = os.path.join(OUT, "spawn_nodes.ico")
    out.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"done  {ico_path}")

    # Also save as the app icon (intricate.ico replacement)
    app_ico = os.path.join(OUT, "intricate.ico")
    out.save(app_ico, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"done  {app_ico}")

    # ── Clean variant — shadow + reddish-brown outline stripped ─────────────
    # Start from the original (pre-shadow-reduction) for a clean pass
    orig = Image.open(SRC).convert("RGBA")
    c_arr = np.array(orig, dtype=np.float64)
    c_r, c_g, c_b, c_a = c_arr[:,:,0], c_arr[:,:,1], c_arr[:,:,2], c_arr[:,:,3]
    c_brightness = (c_r + c_g + c_b) / 3.0
    c_max = np.maximum(np.maximum(c_r, c_g), c_b)
    c_min = np.minimum(np.minimum(c_r, c_g), c_b)
    c_sat = np.where(c_max > 0, (c_max - c_min) / c_max, 0)

    # 1. Strip shadow — dark, low-sat, reddish (same heuristic as main pass)
    c_shadow = (c_brightness < 130) & (c_sat < 0.45) & (c_r > c_b) & (c_a > 0)
    c_arr[:,:,3] = np.where(c_shadow, 0, c_arr[:,:,3]).astype(np.uint8)

    # 2. Strip reddish-brown outline — the border glow from the source image.
    #    These pixels are warm-toned (red dominant, r > b), moderate brightness,
    #    and distinct from the sticker body (purple strokes have b > r or b ≈ r).
    #    Colour-distance from known brown ~(140, 80, 70) catches the outline,
    #    constrained to warm pixels only so the purple strokes survive.
    brown_r, brown_g, brown_b = 140.0, 80.0, 70.0
    dist_brown = np.sqrt(
        (c_r - brown_r)**2 + (c_g - brown_g)**2 + (c_b - brown_b)**2
    )
    is_warm = c_r > c_b + 15   # must be clearly warm, not purple
    is_brown_outline = (dist_brown < 80) & is_warm & (c_arr[:,:,3] > 0)
    c_arr[:,:,3] = np.where(is_brown_outline, 0, c_arr[:,:,3]).astype(np.uint8)

    # 3. Strip any remaining semi-transparent warm fringe at the edges
    c_a2 = c_arr[:,:,3]
    warm_fringe = (c_brightness < 160) & (c_sat < 0.35) & (c_r > c_b) & (c_a2 > 0) & (c_a2 < 240)
    c_arr[:,:,3] = np.where(warm_fringe, 0, c_arr[:,:,3]).astype(np.uint8)

    clean = Image.fromarray(c_arr.astype(np.uint8))

    clean_out = _to_1024(clean, "spawn_nodes_clean.png")
    clean_out.save(os.path.join(OUT, "spawn_nodes_clean_1024.png"))
    print("done  spawn_nodes_clean_1024.png")


if __name__ == "__main__":
    process()
