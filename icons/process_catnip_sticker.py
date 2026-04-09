#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process the catnip sticker from the hand-drawn whiskers reference.

1. Make the drop shadow 50% translucent (same technique as spawn icon)
2. Redraw whiskers — centred, parallel, clean horizontal lines
"""

from PIL import Image, ImageDraw
import numpy as np
import math, os

SRC = os.path.join(os.path.dirname(__file__), "..", "Images", "thingalingswhiskers.png")
OUT = os.path.dirname(__file__)


def process():
    img = Image.open(SRC).convert("RGBA")
    arr = np.array(img, dtype=np.float64)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    # ── 50% translucent drop shadow ──────────────────────────────────────
    # Shadow = dark, low saturation, reddish-brown tint (same as spawn icon)
    brightness = (r + g + b) / 3.0
    max_rgb = np.maximum(np.maximum(r, g), b)
    min_rgb = np.minimum(np.minimum(r, g), b)
    saturation = np.where(max_rgb > 0, (max_rgb - min_rgb) / max_rgb, 0)

    is_dark = brightness < 130
    is_low_sat = saturation < 0.45
    is_reddish = r > b
    is_shadow = is_dark & is_low_sat & is_reddish & (a > 0)

    # Shadow at 80% alpha — needs to be visible on dark UI backgrounds
    new_a = a.copy()
    new_a[is_shadow] = a[is_shadow] * 0.80
    arr[:, :, 3] = new_a.astype(np.uint8)

    # ── Remove hand-drawn whiskers (dark lines in the face area) ─────────
    # The whiskers are dark strokes in the centre of the image
    # Identify: dark pixels (low brightness) that aren't part of the shadow
    # and aren't the pink hearts (high saturation + red)
    h, w = arr.shape[:2]
    face_cx = int(w * 0.40)
    face_cy = int(h * 0.55)
    face_r = int(w * 0.28)

    # Mask for the face area
    yy, xx = np.mgrid[:h, :w]
    in_face = ((xx - face_cx)**2 + (yy - face_cy)**2) < face_r**2

    # Dark non-shadow non-pink pixels in the face = whiskers to remove
    is_pink = (r > 180) & (g < 130) & (b < 160)
    is_whisker = in_face & (brightness < 80) & ~is_pink & (a > 100)
    arr[:, :, 3] = np.where(is_whisker, 0, arr[:, :, 3]).astype(np.uint8)

    img = Image.fromarray(arr.astype(np.uint8))

    # ── Redraw whiskers — centred, parallel, clean ───────────────────────
    draw = ImageDraw.Draw(img)

    whisker_color = (50, 50, 50, 220)
    whisker_w = max(2, w // 130)
    whisker_len = int(w * 0.22)
    gap = int(h * 0.04)

    # Three parallel horizontal lines, centred on the face
    for i in [-1, 0, 1]:
        y = face_cy + i * gap
        x0 = face_cx - whisker_len // 2
        x1 = face_cx + whisker_len // 2
        draw.line([(x0, y), (x1, y)], fill=whisker_color, width=whisker_w)

    # Save full size
    img.save(os.path.join(OUT, "catnip_sticker.png"))
    print(f"done  catnip_sticker.png  ({w}x{h})")

    # ── Clean variant — shadow stripped, for dynamic shadow compositing ───
    clean = img.copy()
    c_arr = np.array(clean, dtype=np.float64)
    c_r, c_g, c_b, c_a = c_arr[:,:,0], c_arr[:,:,1], c_arr[:,:,2], c_arr[:,:,3]
    c_brightness = (c_r + c_g + c_b) / 3.0
    c_max = np.maximum(np.maximum(c_r, c_g), c_b)
    c_min = np.minimum(np.minimum(c_r, c_g), c_b)
    c_sat = np.where(c_max > 0, (c_max - c_min) / c_max, 0)
    c_shadow = (c_brightness < 130) & (c_sat < 0.45) & (c_r > c_b) & (c_a > 0)
    # Remove shadow completely — clean sticker body only
    c_arr[:,:,3] = np.where(c_shadow, 0, c_arr[:,:,3]).astype(np.uint8)
    clean = Image.fromarray(c_arr.astype(np.uint8))
    clean.save(os.path.join(OUT, "catnip_sticker_clean.png"))
    print(f"done  catnip_sticker_clean.png")

    # ── 1024x1024 padded versions ──────────────────────────────────────────
    pad = 20

    def _to_1024(src, name):
        bbox = src.getbbox()
        cropped = src.crop(bbox) if bbox else src
        cw, ch = cropped.size
        side = max(cw, ch)
        canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
        canvas.paste(cropped, ((side + pad * 2 - cw) // 2, (side + pad * 2 - ch) // 2))
        out = canvas.resize((1024, 1024), Image.LANCZOS)
        out.save(os.path.join(OUT, name))
        print(f"done  {name}")

    _to_1024(img,   "catnip_sticker_1024.png")        # with baked shadow (legacy)
    _to_1024(clean, "catnip_sticker_clean_1024.png")   # no shadow — for dynamic compositing


if __name__ == "__main__":
    process()
