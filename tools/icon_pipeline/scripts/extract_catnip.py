#!/usr/bin/env python3
"""Extract the catnip sticker from Thingaling.png.

The source PNG is already 1024x1024 with transparent background —
use it directly without resizing to preserve full quality.

Produces:
  - Thingaling.png  (1024px — used by Theme for the feed button)
  - Thingaling.ico  (multi-resolution ICO)
"""
from PIL import Image

out = Image.open("Images/Stickers/Thingaling.png").convert("RGBA")
print(f"Source: {out.size[0]}x{out.size[1]}")

out.save("icons/Thingaling.png")

# ── Verify on dark background ────────────────────────────────────────
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("Documents/Data/Icon Pipeline/_verify_catnip_dark.png")

# ── Multi-resolution ICO ─────────────────────────────────────────────
out.save("icons/Thingaling.ico", format="ICO",
         sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]])

print("Done — Thingaling.png + Thingaling.ico")
