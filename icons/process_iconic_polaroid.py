#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process the hand-painted 'Iconic Polaroid.png' into the polaroid
icon family (1024 PNG + multi-resolution ICO).

The source is 1920x1080 RGB with a solid (40, 40, 40) dark background
and cream (225, 213, 198) line art.  This script:

  1. Center-crops to 1080x1080 square.
  2. Reverse-composites the flat-background render into cream+alpha,
     so anti-aliased edges get correct partial transparency.
  3. Downscales to 1024x1024 with LANCZOS.
  4. Saves as icons/polaroid.png and multi-resolution .ico.
"""

import numpy as np
from PIL import Image
from pathlib import Path

HERE   = Path(__file__).resolve().parent
SRC    = HERE / 'Iconic Polaroid.png'
OUT_PNG = HERE / 'polaroid.png'
OUT_ICO = HERE / 'polaroid.ico'

BG    = np.array([40, 40, 40],   dtype=np.float32)
CREAM = np.array([225, 213, 198], dtype=np.float32)

src = np.asarray(Image.open(SRC).convert('RGB'), dtype=np.float32)
h, w = src.shape[:2]

# Center crop to square
s = min(h, w)
y0 = (h - s) // 2
x0 = (w - s) // 2
cropped = src[y0:y0 + s, x0:x0 + s]

# Reverse-composite: observed = cream * a + bg * (1-a)
# => a = (observed - bg) / (cream - bg)
# Use max over channels to keep sharp edges even if source has subtle
# color deviation.
denom = CREAM - BG
alpha_channels = np.clip((cropped - BG) / denom, 0.0, 1.0)
alpha = np.max(alpha_channels, axis=2)
alpha_u8 = (alpha * 255.0 + 0.5).astype(np.uint8)

rgba = np.zeros((s, s, 4), dtype=np.uint8)
rgba[..., 0] = int(CREAM[0])
rgba[..., 1] = int(CREAM[1])
rgba[..., 2] = int(CREAM[2])
rgba[..., 3] = alpha_u8

out = Image.fromarray(rgba, 'RGBA').resize((1024, 1024), Image.LANCZOS)
out.save(OUT_PNG)

sizes = [16, 24, 32, 48, 64, 128, 256]
out.save(OUT_ICO, format='ICO', sizes=[(z, z) for z in sizes])

print(f'wrote {OUT_PNG}')
print(f'wrote {OUT_ICO}')
