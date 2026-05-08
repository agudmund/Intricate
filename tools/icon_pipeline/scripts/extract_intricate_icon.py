#!/usr/bin/env python3
"""Rebuild Intricate.ico + Intricate.png from the official sticker source.

Source: Images/Stickers/Intricate Official Iconic Icon.png (928x1152, RGBA)
Background is already transparent — trim, square, resize to 1024.
"""
from PIL import Image

src = Image.open("Images/Stickers/Intricate Official Iconic Icon.png").convert("RGBA")
print(f"Source: {src.size[0]}x{src.size[1]}")

# Trim transparent edges
bbox = src.getbbox()
if bbox:
    src = src.crop(bbox)
cw, ch = src.size
print(f"Trimmed: {cw}x{ch}")

# Square with slight padding
side = int(max(cw, ch) * 1.1)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(src, ((side - cw) // 2, (side - ch) // 2))

# Resize to 1024
out = square.resize((1024, 1024), Image.LANCZOS)
out.save("icons/Intricate.png")

# Verify on dark background
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("icons/_verify_intricate_dark.png")

# Multi-resolution ICO
out.save("icons/Intricate.ico", format="ICO",
         sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]])

print("Done — Intricate.png (1024px) + Intricate.ico (7 frames)")
