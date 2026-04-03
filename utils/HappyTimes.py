#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/HappyTimes.py PNG metadata helpers
-Read and write tEXt stamps in PNG files without touching pixel data for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from utils.logger import setup_logger

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
    Write a tEXt metadata chunk into a PNG file.

    Preserves all existing tEXt chunks. If *key* already exists it is
    replaced. Silently no-ops for non-PNG files, missing files, or if
    Pillow is absent.
    """
    if path.suffix.lower() != ".png":
        return
    try:
        from PIL import Image, PngImagePlugin
        with Image.open(path) as img:
            info = PngImagePlugin.PngInfo()
            for k, v in (img.text or {}).items():
                if k != key:
                    info.add_text(k, v)
            info.add_text(key, value)
            img.save(path, "PNG", pnginfo=info)
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
