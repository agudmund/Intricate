#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/hex_extract.py hex colour extraction
-Reading colours out of any text where someone wrote them down, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re
from pathlib import Path

# Matches #RGB, #RRGGBB, #RRGGBBAA. Word-boundary anchored on the right
# so adjacent identifiers don't bleed into the match.
_HEX_RE = re.compile(r'#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')


def extract_hex_colors(text: str) -> list[dict]:
    """Pure text → unique hex colours as palette-ready dicts.

    Returns a list of ``{"label": h, "hex": h}`` entries — one per unique
    hex value (case-insensitive dedup, first-occurrence label preserved).
    Empty list if the text has no hex literals or is empty.

    The dict shape matches what ``PaletteNodeData`` consumes via
    ``Scene.add_palette_node(colors=...)``, so callers can pipe the
    return value straight through without reshaping.
    """
    if not text:
        return []
    raw = _HEX_RE.findall(text)
    seen: set[str] = set()
    colors: list[dict] = []
    for h in raw:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            colors.append({"label": h, "hex": h})
    return colors


def extract_hex_colors_from_file(path) -> list[dict]:
    """Convenience: read a file and extract hex colours from its contents.

    Returns an empty list on read errors (missing file, permission denied,
    encoding mismatch). Best-effort: errors are absorbed silently because
    callers typically use this in drag-drop or file-browser contexts where
    a non-readable file is just "no palette here", not an error condition.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return extract_hex_colors(text)
