#!/usr/bin/env python3
"""Generate github_desktop icon — GitHub octocat with lavender-grey palette from reference."""
from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2

# Colour scheme from the reference icon
RING   = (180, 175, 195, 255)    # muted purple-grey outer ring
FILL   = (215, 212, 225, 0)      # fully transparent disc — node color shines through
CAT    = (255, 255, 255, 255)    # fully opaque white contour lines

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Filled disc behind the octocat
draw.ellipse([cx-800, cy-800, cx+800, cy+800], fill=FILL, outline=RING, width=52)

# ── Octocat silhouette ───────────────────────────────────────────────────

# Head circle
head_r = 340
draw.ellipse(
    [cx - head_r, cy - head_r + 20, cx + head_r, cy + head_r + 20],
    outline=CAT, width=38,
)

# Left ear
ear_pts_l = [
    (cx - 300, cy - 200),
    (cx - 380, cy - 420),
    (cx - 180, cy - 310),
]
draw.line(ear_pts_l, fill=CAT, width=38, joint="curve")

# Right ear
ear_pts_r = [
    (cx + 300, cy - 200),
    (cx + 380, cy - 420),
    (cx + 180, cy - 310),
]
draw.line(ear_pts_r, fill=CAT, width=38, joint="curve")

# Eyes — two filled ellipses
eye_r = 50
eye_y = cy - 30
draw.ellipse([cx - 160 - eye_r, eye_y - eye_r, cx - 160 + eye_r, eye_y + eye_r], fill=CAT)
draw.ellipse([cx + 160 - eye_r, eye_y - eye_r, cx + 160 + eye_r, eye_y + eye_r], fill=CAT)

# Nose/mouth — small line
draw.line([(cx - 30, cy + 80), (cx + 30, cy + 80)], fill=CAT, width=20)

# Tentacle tail at bottom
draw.arc(
    [cx - 120, cy + 200, cx + 120, cy + 440],
    0, 180, fill=CAT, width=30,
)

# Downsample to 1024
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/github_desktop.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/github_desktop.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:],
)
print("Created github_desktop.png + .ico")
