#!/usr/bin/env python3
"""Extract the 4th icon (octocat) from ConsistentIcon.png strip and produce github_desktop icon."""
from PIL import Image
import numpy as np

src = Image.open("Images/ConsistentIcon.png").convert("RGBA")
w, h = src.size

# The strip has 4 roughly equal icons — grab the rightmost quarter
quarter = w // 4
# Crop the 4th icon with a small inward margin to avoid neighbours
left = quarter * 3
crop = src.crop((left, 0, w, h))

# Remove the dark purple background — sample bg color from corner
arr = np.array(crop, dtype=np.float32)
# Background is roughly (74, 58, 90) from the dark purple
bg = np.array([74, 58, 90], dtype=np.float32)
tolerance = 55.0

# Distance from background color
dist = np.sqrt(np.sum((arr[:, :, :3] - bg) ** 2, axis=2))
# Make background pixels transparent
mask = dist < tolerance
arr[mask, 3] = 0

# Remove the drop shadow underneath — everything below the main body
# Find the lowest row that has bright (non-shadow) content
brightness = np.max(arr[:, :, :3], axis=2)
has_bright = brightness > 150
# Per-row: does this row have any bright pixel?
bright_rows = np.any(has_bright & (arr[:, :, 3] > 0), axis=1)
last_bright = np.max(np.where(bright_rows)) if np.any(bright_rows) else arr.shape[0]
# Wipe everything below the last bright row
arr[last_bright + 1:, :, 3] = 0
# In the bottom 15%, remove dark/dim pixels (the shadow fringe)
fringe_start = int(arr.shape[0] * 0.85)
for y in range(fringe_start, arr.shape[0]):
    for x in range(arr.shape[1]):
        if arr[y, x, 3] > 0 and brightness[y, x] < 180:
            arr[y, x, 3] = 0

result = Image.fromarray(arr.astype(np.uint8))

# Trim transparent edges
bbox = result.getbbox()
if bbox:
    result = result.crop(bbox)

# Make square by padding the shorter axis
cw, ch = result.size
side = max(cw, ch)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(result, ((side - cw) // 2, (side - ch) // 2))

# Resize to 1024
out = square.resize((1024, 1024), Image.LANCZOS)
out.save("icons/github_desktop.png")

# Multi-resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    "icons/github_desktop.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:],
)
print(f"Extracted icon {cw}x{ch} -> 1024x1024 png + ico")
