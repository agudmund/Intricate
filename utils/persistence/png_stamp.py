#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/persistence/png_stamp.py tEXt chunk helpers
-Plaintext metadata on PNG files without disturbing the pixels for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import struct
import zlib
from pathlib import Path

from shared_braincell.logger import setup_logger

_log = setup_logger("png_stamp")

# Semantic key Intricate stamps vision-derived captions under.  Any file
# carrying this key has been processed through the vision pipeline; the
# stamp itself is the record, so re-uploading stamped files to the API
# is avoided automatically.
_INTRICATE_VISION_KEY = "intricate_vision"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ─────────────────────────────────────────────────────────────────────────
# GENERIC tEXt CHUNK READ/WRITE
# ─────────────────────────────────────────────────────────────────────────

def read_png_stamp(path: Path, key: str) -> str | None:
    """Return the tEXt value stored under *key* in the PNG at *path*, or
    None if the key is absent, the file is not a PNG, or the read fails."""
    if path.suffix.lower() != ".png":
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(_PNG_SIGNATURE):
        return None

    key_bytes = key.encode("latin-1")
    pos = len(_PNG_SIGNATURE)
    n = len(data)
    while pos + 12 <= n:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_end = pos + 12 + length   # length(4) + type(4) + data(length) + crc(4)
        if chunk_end > n:
            break
        if chunk_type == b"tEXt":
            chunk_data = data[pos + 8:pos + 8 + length]
            null_idx = chunk_data.find(b"\x00")
            if null_idx >= 0 and chunk_data[:null_idx] == key_bytes:
                try:
                    return chunk_data[null_idx + 1:].decode("latin-1")
                except UnicodeDecodeError:
                    return None
        pos = chunk_end
    return None


def write_png_stamp(path: Path, key: str, value: str) -> bool:
    """Write or replace a tEXt chunk with the given *key* in the PNG at
    *path*.  Returns True on successful write, False otherwise.

    Silently declines non-PNG files, missing files, and IO errors — the
    stamp is advisory, not enforced.  Pixel data and all non-matching
    chunks are byte-for-byte preserved; only the tEXt chunk matching
    *key* is replaced (or freshly inserted after IHDR if absent)."""
    if path.suffix.lower() != ".png":
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not data.startswith(_PNG_SIGNATURE):
        return False

    key_bytes = key.encode("latin-1")
    new_payload = key_bytes + b"\x00" + value.encode("latin-1")
    new_crc = struct.pack(
        ">I", zlib.crc32(b"tEXt" + new_payload) & 0xFFFFFFFF
    )

    out = bytearray(_PNG_SIGNATURE)
    inserted = False
    pos = len(_PNG_SIGNATURE)
    n = len(data)

    while pos + 12 <= n:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        chunk_end = pos + 12 + length

        # Drop any existing tEXt chunk carrying our key — we're about to
        # insert the replacement after IHDR.
        if chunk_type == b"tEXt":
            null_idx = chunk_data.find(b"\x00")
            if null_idx >= 0 and chunk_data[:null_idx] == key_bytes:
                pos = chunk_end
                continue

        out += data[pos:chunk_end]

        # Fresh tEXt chunk slots in immediately after the IHDR.
        if not inserted and chunk_type == b"IHDR":
            out += struct.pack(">I", len(new_payload))
            out += b"tEXt" + new_payload + new_crc
            inserted = True

        pos = chunk_end

    if not inserted:
        # Malformed PNG with no IHDR — refuse to write garbage.
        return False

    try:
        path.write_bytes(bytes(out))
        _log.debug(f"[png_stamp] wrote {path.name!r} [{key}] = {value!r}")
        return True
    except OSError as exc:
        _log.warning(f"[png_stamp] write failed for {path.name!r}: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────
# INTRICATE VISION STAMP — thin convenience wrappers
# ─────────────────────────────────────────────────────────────────────────

def read_png_vision_stamp(path: Path) -> str | None:
    """Return the Intricate vision caption stored in *path*'s tEXt
    metadata, or None if absent."""
    return read_png_stamp(path, _INTRICATE_VISION_KEY)


def write_png_vision_stamp(path: Path, caption: str) -> bool:
    """Store an Intricate vision caption in *path*'s tEXt metadata.
    Returns True on successful write."""
    return write_png_stamp(path, _INTRICATE_VISION_KEY, caption)
