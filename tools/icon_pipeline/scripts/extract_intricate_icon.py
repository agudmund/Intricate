#!/usr/bin/env python3
"""Rebuild Intricate.ico from the source-of-truth Intricate.png.

The PNG at icons/Intricate.png is the authored brand mark — replace it
whenever the brand evolves and re-run this script to regenerate the
multi-resolution .ico Windows reads from for the taskbar / tray /
shortcut.  No trim or resize: the PNG is taken as-is so what the user
authored is what ships.

Pairs with project_curtains_icon_is_family_fallback memory — Intricate's
brand mark is the share-arrow shape, also doubles as Theme.iconCurtains
fallback.
"""
from PIL import Image

SRC = "icons/Intricate.png"
ICO = "icons/Intricate.ico"
VERIFY = "icons/_verify_intricate_dark.png"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

src = Image.open(SRC).convert("RGBA")
print(f"Source: {SRC}  {src.size[0]}x{src.size[1]}  mode={src.mode}")

# Verify on the node-background colour to catch any baked-in white
# fringes on semi-transparent edges before they ship.  Same dark bg
# the sticker pipeline uses.
dark_bg = Image.new("RGBA", src.size, (45, 52, 54, 255))
dark_bg.paste(src, (0, 0), src)
dark_bg.save(VERIFY)

# Multi-resolution ICO — Pillow downsamples each frame from the source.
# Windows picks the sharpest layer for the size it needs (taskbar 32,
# tray 16, large icons 256, etc.).
src.save(ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

print(f"Done — {ICO} ({len(ICO_SIZES)} frames: {ICO_SIZES})")
print(f"Verify: {VERIFY}")
