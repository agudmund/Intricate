#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/HappyHelper.py PNG metadata inspector
-Reads and prints every metadata field from a PNG file for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences

Usage:
    python utils/HappyHelper.py path/to/image.png
"""

import sys
from pathlib import Path


def inspect_png(path: str | Path) -> dict:
    """
    Read all available metadata from a PNG file.

    Returns a dict with keys:
        format   — format string, dimensions, color mode
        info     — PNG info dict (tEXt chunks, gamma, dpi, etc.)
        exif     — EXIF tags dict (may be empty)
        chunks   — list of (type, length) for every raw PNG chunk
    """
    from PIL import Image
    from PIL.ExifTags import TAGS

    path = Path(path)
    result = {"format": {}, "info": {}, "exif": {}, "chunks": []}

    with Image.open(path) as img:
        result["format"] = {
            "type": img.format,
            "size": f"{img.size[0]}x{img.size[1]}",
            "mode": img.mode,
        }
        result["info"] = dict(img.info)
        exif = img.getexif()
        if exif:
            result["exif"] = {TAGS.get(k, k): v for k, v in exif.items()}

    # Raw chunk scan — no Pillow, just the binary structure
    import struct
    data = path.read_bytes()
    pos = 8  # skip PNG signature
    text_chunks = {}
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        chunk_type_raw = data[pos+4:pos+8]
        chunk_type = chunk_type_raw.decode('ascii', errors='replace')
        chunk_data = data[pos+8:pos+8+length]
        result["chunks"].append((chunk_type, length))
        # Extract tEXt key/value pairs directly from binary
        if chunk_type_raw == b'tEXt':
            null_idx = chunk_data.find(b'\x00')
            if null_idx >= 0:
                k = chunk_data[:null_idx].decode('latin-1', errors='replace')
                v = chunk_data[null_idx+1:].decode('latin-1', errors='replace')
                text_chunks[k] = v
        pos += 12 + length

    # Merge binary-parsed tEXt into info (overrides Pillow's if present)
    result["info"].update(text_chunks)

    return result


def print_report(path: str | Path) -> None:
    """Print a human-readable metadata report for a PNG file."""
    path = Path(path)
    meta = inspect_png(path)

    print(f"=== {path.name} ===")
    print(f"Format: {meta['format']['type']}  {meta['format']['size']}  {meta['format']['mode']}")

    print("\n--- PNG Info ---")
    for k, v in meta["info"].items():
        val = repr(v) if len(str(v)) > 120 else str(v)
        print(f"  {k}: {val}")

    if meta["exif"]:
        print("\n--- EXIF ---")
        for k, v in meta["exif"].items():
            print(f"  {k}: {v}")

    print("\n--- Chunks ---")
    for chunk_type, length in meta["chunks"]:
        print(f"  {chunk_type}  {length:>8} bytes")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python utils/HappyHelper.py <image.png>")
        sys.exit(1)
    print_report(sys.argv[1])
