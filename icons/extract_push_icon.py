#!/usr/bin/env python3
"""Extract the 5th icon (push arrow) from pushIconHigsRes.png strip."""
from PIL import Image
import numpy as np

src = Image.open("Images/pushIconHigsRes.png").convert("RGBA")
w, h = src.size

# 5 icons in the strip — the arrow is rightmost, crop generously from right
# Image is 1024x256, arrow starts around x=860
crop = src.crop((int(w * 0.84), 0, w, h))

# Remove the grey-brown background — sample from multiple corners for robustness
arr = np.array(crop, dtype=np.float32)
corners = [arr[2, 2, :3], arr[2, -3, :3], arr[-3, 2, :3], arr[-3, -3, :3]]
bg = np.mean(corners, axis=0)
tolerance = 65.0
dist = np.sqrt(np.sum((arr[:, :, :3] - bg) ** 2, axis=2))
arr[dist < tolerance, 3] = 0

# Second pass — any remaining brownish/reddish fringe pixels
# The arrow is purple/white/dark-blue, so warm-brown pixels are background
for y in range(arr.shape[0]):
    for x in range(arr.shape[1]):
        if arr[y, x, 3] == 0:
            continue
        r, g, b = arr[y, x, :3]
        # Brown/reddish fringe: red channel dominates, low blue
        if r > 80 and r > b * 1.15 and g < 140 and b < 140:
            arr[y, x, 3] = 0

result = Image.fromarray(arr.astype(np.uint8))

# Trim transparent edges
bbox = result.getbbox()
if bbox:
    result = result.crop(bbox)

# Make square
cw, ch = result.size
side = max(cw, ch)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(result, ((side - cw) // 2, (side - ch) // 2))

# Resize to 1024
out = square.resize((1024, 1024), Image.LANCZOS)
out.save("icons/git_push.png")

# Multi-resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
out.save("icons/git_push.ico", format="ICO", sizes=[(s, s) for s in sizes])
print(f"Extracted push icon {cw}x{ch} -> 1024x1024 png + ico")
