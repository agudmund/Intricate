#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the audio group sidebar icon — sound wave / speaker waveform.
Three curved arcs radiating from a speaker shape, representing audio output.
"""

from PIL import Image, ImageDraw
import math

S  = 2048
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — identical across all sidebar icons
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

w = 28   # stroke width

# Speaker body — small rectangle on the left
draw.rounded_rectangle(
    [cx - 320, cy - 120, cx - 160, cy + 120],
    radius=20, outline=C, width=w
)

# Speaker cone — trapezoid as two angled lines
draw.line([(cx - 160, cy - 120), (cx - 40, cy - 240)], fill=C, width=w)
draw.line([(cx - 160, cy + 120), (cx - 40, cy + 240)], fill=C, width=w)
draw.line([(cx - 40, cy - 240), (cx - 40, cy + 240)], fill=C, width=w)

# Sound wave arcs — three concentric arcs radiating right
for i, radius in enumerate([180, 300, 420]):
    arc_bbox = [cx + 60 - radius, cy - radius, cx + 60 + radius, cy + radius]
    draw.arc(arc_bbox, start=-45, end=45, fill=C, width=w)

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/audio_group.png')

# Multi-resolution ICO
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/audio_group.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)

print("audio_group.png + .ico written")
