#!/usr/bin/env python3
"""Extract the scissors sticker from trimAudioling.png.

The sticker has layers from outside in:
  1. White background (outside) → remove
  2. Red dashed cut-line → remove
  3. White thick sticker peel border → KEEP
  4. Grey scissors with dark outline → KEEP

Strategy: flood-fill from the image corners to identify the outer background,
then remove the red dashes.  Everything inside the dashed line stays,
including the white sticker border.  Defringe only the outermost edge
against transparent.
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label
from collections import deque

src = Image.open("Images/trimAudioling.png").convert("RGBA")
arr = np.array(src, dtype=np.float32)
h, w = arr.shape[:2]
r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

# ── Step 1: Flood-fill from corners to find OUTER background ─────────
# The outer background is white/near-white.  We flood from all four
# corners and mark connected white pixels as background.  The white
# sticker border is separated from the outer white by the red dashes
# and a thin gap, so the flood won't cross into it.
def is_outer(y, x):
    """A pixel is outer if it's already transparent or is a red dash."""
    if a[y, x] < 10:
        return True  # already-transparent outer background
    # Red/pink dashed border — these sit between outer bg and sticker border
    return (r[y, x] > 120 and r[y, x] > g[y, x] + 15 and r[y, x] > b[y, x] + 15)

# BFS flood from corners — only pass through transparent pixels and red
# dashes.  STOP at any opaque pixel (the white sticker border has α=255).
outer = np.zeros((h, w), dtype=bool)
visited = np.zeros((h, w), dtype=bool)

seeds = []
for x in range(w):
    seeds.extend([(0, x), (h-1, x)])
for y in range(h):
    seeds.extend([(y, 0), (y, w-1)])

queue = deque()
for sy, sx in seeds:
    if not visited[sy, sx] and is_outer(sy, sx):
        queue.append((sy, sx))
        visited[sy, sx] = True
        outer[sy, sx] = True

while queue:
    cy, cx = queue.popleft()
    for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
        ny, nx = cy + dy, cx + dx
        if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
            visited[ny, nx] = True
            if is_outer(ny, nx):
                outer[ny, nx] = True
                queue.append((ny, nx))

# Kill outer background + red dashes
a[outer] = 0
arr[:, :, 3] = a

# ── Step 2: Kill any remaining red dash fragments inside ─────────────
# Some red dots may be stranded inside if the flood didn't reach them
alive = a > 0
red_inside = alive & (r > 140) & (r > g + 30) & (r > b + 30)
a[red_inside] = 0
arr[:, :, 3] = a

# ── Step 3: Keep largest connected component ─────────────────────────
alpha_mask = a > 0
labeled, n = label(alpha_mask)
if n > 0:
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    biggest = sizes.argmax()
    a[labeled != biggest] = 0
    arr[:, :, 3] = a

# ── Step 4: Defringe outermost edge against white ────────────────────
# Only semi-transparent edge pixels need decontamination — the solid
# white sticker border (alpha=255) stays untouched.
alpha_norm = np.clip(a / 255.0, 0.001, 1.0)
semi_transparent = (a > 0) & (a < 250)
for ch in range(3):
    original = arr[:, :, ch]
    decontaminated = (original - 255.0 * (1.0 - alpha_norm)) / alpha_norm
    # Only apply to semi-transparent pixels — leave solid pixels alone
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
out.save("icons/trimAudio.png")

# ── Verify: composite on dark node background ────────────────────────
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("icons/_verify_trimAudio_dark.png")

# Multi-resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
out.save("icons/trimAudio.ico", format="ICO", sizes=[(s, s) for s in sizes])
print(f"Extracted trim audio sticker {cw}x{ch_px} -> 1024x1024 png + ico")
