#!/usr/bin/env python3
"""Extract the awake-state sticker from Images/Stickers/Awake.png.

Unlike play/pause/return, the awake sticker is a multi-heart composition
with hearts intentionally clustered in the upper-left of the canvas — so
the pipeline skips both the largest-component step (which would drop the
two smaller hearts) and the trim+pad step (which would re-centre the
composition away from its dripping-from-Thingaling corner placement).
Source is already 1024×1024 with clean alpha; all we need is the white-
matte defringe on semi-transparent edges.
"""
from PIL import Image
import numpy as np

src = Image.open("Images/Stickers/Awake.png").convert("RGBA")
arr = np.array(src, dtype=np.float32)
r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

# ── Defringe against white matte ─────────────────────────────────────
# Anti-aliased edge pixels carry baked-in white from the source matte.
# Reverse the compositing math:  actual = (observed - 255*(1-α)) / α.
alpha_norm = np.clip(a / 255.0, 0.001, 1.0)
semi_transparent = (a > 0) & (a < 250)
for ch in range(3):
    original = arr[:, :, ch]
    decontaminated = (original - 255.0 * (1.0 - alpha_norm)) / alpha_norm
    arr[:, :, ch] = np.where(semi_transparent, np.clip(decontaminated, 0, 255), original)

out = Image.fromarray(arr.astype(np.uint8))
# Source is already 1024×1024 and the hearts' upper-left placement IS the
# composition — no trim, no resize. Save as-is.
out.save("icons/awakeIconic.png")

# Verify: composite on dark node background
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("icons/_verify_awake_dark.png")

# Multi-resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
out.save("icons/awakeIconic.ico", format="ICO", sizes=[(s, s) for s in sizes])
print("Extracted awake sticker 1024x1024 -> png + ico")
