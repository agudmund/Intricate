#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/text_chunker.py text chunker for oversized paste splits
-The last of the text chunker learnt to break gently at paragraph seams before anything else, For enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from __future__ import annotations


# Default paste threshold — content larger than this gets split into a chain
# of nodes instead of rendered in a single QTextEdit. 50 KB is well above
# normal prose (a long chapter is ~30–50 KB) and comfortably below the sizes
# where Qt's text layout starts costing real frames.
DEFAULT_CHUNK_CHARS = 50_000


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split *text* into chunks each at most *max_chars* long, preferring
    gentle break points.

    Cascades through progressively finer separators: paragraph
    (``\\n\\n``) → line (``\\n``) → sentence (``. ``) → word (`` ``).
    If even word-level packing still leaves a chunk too big (pathological
    case: a single unbroken glyph run), the chunk is hard-cut on character
    boundaries as a last resort.

    The goal is always that the user's content survives intact across
    chunk boundaries — only the container splits, never the meaning.
    """
    if len(text) <= max_chars:
        return [text]

    for sep in ('\n\n', '\n', '. ', ' '):
        chunks = _greedy_pack(text, sep, max_chars)
        if all(len(c) <= max_chars for c in chunks):
            return chunks

    # Last resort — no natural break fits. Hard-cut on character boundaries
    # so a pathological blob (e.g. a DNA sequence, a minified blob) still
    # lands in finite-size nodes rather than crashing the scene.
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def _greedy_pack(text: str, sep: str, max_chars: int) -> list[str]:
    """Split *text* by *sep* then greedily pack adjacent pieces into chunks
    no larger than *max_chars*. Preserves the separator when rejoining so
    the output remains readable as the original with chunk boundaries
    drawn between natural seams."""
    pieces = text.split(sep)
    if len(pieces) == 1:
        return pieces   # Separator not found — caller will cascade

    out: list[str] = []
    current = pieces[0]
    for piece in pieces[1:]:
        candidate = current + sep + piece
        if len(candidate) > max_chars and current:
            out.append(current)
            current = piece
        else:
            current = candidate
    out.append(current)
    return out
