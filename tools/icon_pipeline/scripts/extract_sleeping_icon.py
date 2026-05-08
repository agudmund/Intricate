#!/usr/bin/env python3
"""Extract the sleeping-state sticker from Images/Stickers/Sleep.png.

The pair-partner to the awake sticker — a purple sleep mask with closed
eye slits and white peel outer. Unlike the awake sticker (multi-heart
composition preserved as-is), this is a single centred shape so the
standard pipeline applies: largest-component cleanup → white-matte
defringe → trim, square, 1024 resize → PNG + multi-res ICO.
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label

src = Image.open("Images/Stickers/Sleep.png").convert("RGBA")
arr = np.array(src, dtype=np.float32)
r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

# ── Keep largest connected component (kills stray dots) ──────────────
alpha_mask = a > 0
labeled, n = label(alpha_mask)
if n > 0:
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    biggest = sizes.argmax()
    a[labeled != biggest] = 0
    arr[:, :, 3] = a

# ── Defringe against white matte ─────────────────────────────────────
alpha_norm = np.clip(a / 255.0, 0.001, 1.0)
semi_transparent = (a > 0) & (a < 250)
for ch in range(3):
    original = arr[:, :, ch]
    decontaminated = (original - 255.0 * (1.0 - alpha_norm)) / alpha_norm
    arr[:, :, ch] = np.where(semi_transparent, np.clip(decontaminated, 0, 255), original)

result = Image.fromarray(arr.astype(np.uint8))

# Trim transparent edges
bbox = result.getbbox()
if bbox:
    result = result.crop(bbox)

# Square with slight padding
cw, ch_px = result.size
side = int(max(cw, ch_px) * 1.1)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(result, ((side - cw) // 2, (side - ch_px) // 2))

# Resize to 1024
out = square.resize((1024, 1024), Image.LANCZOS)
out.save("icons/sleepingIconic.png")

# Verify: composite on dark node background
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("Documents/Data/Icon Pipeline/_verify_sleeping_dark.png")

# Multi-resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
out.save("icons/sleepingIconic.ico", format="ICO", sizes=[(s, s) for s in sizes])
print(f"Extracted sleeping sticker {cw}x{ch_px} -> 1024x1024 png + ico")
