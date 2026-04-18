#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/HappyTimes.py PNG metadata helpers
-Read and write tEXt stamps in PNG files without touching pixel data for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("happytimes")

_DEFAULT_KEY = "intricate_vision"   # legacy default for vision stamps


# ---------------------------------------------------------------------------
# Generic PNG tEXt helpers
# ---------------------------------------------------------------------------

def read_png_stamp(path: Path, key: str = _DEFAULT_KEY) -> str | None:
    """
    Read a tEXt metadata value from a PNG file.

    Returns the stored string for *key*, or None if the key is absent,
    the file is not a PNG, or Pillow is unavailable.
    """
    if path.suffix.lower() != ".png":
        return None
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.text.get(key)
    except Exception:
        return None


def write_png_stamp(path: Path, key: str, value: str) -> None:
    """
    Insert or replace a single tEXt chunk in a PNG file.

    Works at the binary chunk level — reads the raw file bytes, strips any
    existing chunk with the same *key*, inserts the new tEXt chunk before
    IEND, and writes back. Pixel data and all other chunks are untouched
    (byte-for-byte identical), so the file size delta is just the new chunk.

    Silently no-ops for non-PNG files, missing files, or on any error.
    """
    if path.suffix.lower() != ".png":
        return
    try:
        import struct, zlib
        data = path.read_bytes()

        _PNG_SIG = b'\x89PNG\r\n\x1a\n'
        if not data.startswith(_PNG_SIG):
            return

        # Parse existing chunks, drop any tEXt chunk matching our key
        chunks = []
        pos = 8  # skip signature
        while pos < len(data):
            length = struct.unpack('>I', data[pos:pos+4])[0]
            chunk_type = data[pos+4:pos+8]
            chunk_data = data[pos+8:pos+8+length]
            chunk_crc  = data[pos+8+length:pos+12+length]
            # Drop existing tEXt chunk with same key
            if chunk_type == b'tEXt':
                null_idx = chunk_data.find(b'\x00')
                if null_idx >= 0 and chunk_data[:null_idx] == key.encode('latin-1'):
                    pos += 12 + length
                    continue
            chunks.append((chunk_type, chunk_data, chunk_crc))
            pos += 12 + length

        # Build the new tEXt chunk
        text_payload = key.encode('latin-1') + b'\x00' + value.encode('latin-1')
        text_crc = struct.pack('>I', zlib.crc32(b'tEXt' + text_payload) & 0xffffffff)
        text_chunk = (b'tEXt', text_payload, text_crc)

        # Reassemble: signature + all chunks (insert tEXt after IHDR, before IDAT)
        out = bytearray(_PNG_SIG)
        inserted = False
        for chunk_type, chunk_data, chunk_crc in chunks:
            out += struct.pack('>I', len(chunk_data))
            out += chunk_type + chunk_data + chunk_crc
            if not inserted and chunk_type == b'IHDR':
                out += struct.pack('>I', len(text_chunk[1]))
                out += b'tEXt' + text_chunk[1] + text_chunk[2]
                inserted = True

        path.write_bytes(bytes(out))
        _log.debug(f"stamped '{path.name}' [{key}] → {value!r}")
    except Exception as exc:
        _log.debug(f"stamp write skipped for '{path.name}' [{key}]: {exc}")


def read_all_png_stamps(path: Path) -> dict[str, str]:
    """
    Read all tEXt metadata from a PNG file.

    Returns a dict of key→value pairs, or an empty dict on failure.
    """
    if path.suffix.lower() != ".png":
        return {}
    try:
        from PIL import Image
        with Image.open(path) as img:
            return dict(img.text or {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Vision-specific convenience wrappers (backwards compatible)
# ---------------------------------------------------------------------------

def read_png_vision_stamp(path: Path) -> str | None:
    """Read the vision caption from a PNG's tEXt metadata."""
    return read_png_stamp(path, _DEFAULT_KEY)


def write_png_vision_stamp(path: Path, caption: str) -> None:
    """Write a vision caption into a PNG's tEXt metadata."""
    write_png_stamp(path, _DEFAULT_KEY, caption)
