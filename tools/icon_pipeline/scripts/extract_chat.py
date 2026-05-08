#!/usr/bin/env python3
"""Extract the Chat sticker from Chat.png for The Settlers shortcut icon.

Sticker has white background → remove, keep white peel border + purple
chat bubbles.  Output ICO to The Settlers/icons/.
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label
from collections import deque

src = Image.open("Images/Stickers/Chat.png").convert("RGBA")
arr = np.array(src, dtype=np.float32)
h, w = arr.shape[:2]
r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

# ── Step 1: Flood-fill from corners to find OUTER background ─────────
def is_outer_white(y, x):
    if a[y, x] < 10:
        return True
    return (r[y, x] > 240 and g[y, x] > 240 and b[y, x] > 240 and a[y, x] > 200)

outer = np.zeros((h, w), dtype=bool)
visited = np.zeros((h, w), dtype=bool)

seeds = []
for x in range(w):
    seeds.extend([(0, x), (h-1, x)])
for y in range(h):
    seeds.extend([(y, 0), (y, w-1)])

queue = deque()
for sy, sx in seeds:
    if not visited[sy, sx] and is_outer_white(sy, sx):
        queue.append((sy, sx))
        visited[sy, sx] = True
        outer[sy, sx] = True

while queue:
    cy, cx = queue.popleft()
    for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
        ny, nx = cy + dy, cx + dx
        if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
            visited[ny, nx] = True
            if is_outer_white(ny, nx):
                outer[ny, nx] = True
                queue.append((ny, nx))

a[outer] = 0
arr[:, :, 3] = a

# ── Step 2: Keep largest connected component ─────────────────────────
alpha_mask = a > 0
labeled, n = label(alpha_mask)
if n > 0:
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    biggest = sizes.argmax()
    a[labeled != biggest] = 0
    arr[:, :, 3] = a

# ── Step 3: Defringe edge pixels against white ───────────────────────
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

# ── Verify: composite on dark background ─────────────────────────────
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("Documents/Data/Icon Pipeline/_verify_chat_dark.png")

# Multi-resolution ICO → The Settlers
ico_path = "../The Settlers/icons/Chat.ico"
sizes = [16, 24, 32, 48, 64, 128, 256]
out.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
print(f"Extracted chat sticker {cw}x{ch_px} -> {ico_path}")
