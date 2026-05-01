#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/label_cleanup.py label prettifier and structural filter
-Shared syntax-cleanup helpers used by every node that spawns AboutNodes from source text, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re

# Characters that, on their own, indicate markdown structure rather than
# content — horizontal rules (`---`, `***`, `___`), setext-style heading
# underlines (`===`), table separators, and decorative dividers like
# `--- --- ---`.  A paragraph consisting only of these (after ignoring
# whitespace) is source scaffolding, not something the reader needs a
# node for.  Skipped at spawn time — the content stays in the source,
# it just doesn't clutter the spawn chain.
_STRUCTURAL_CHARS = set("-=*_ \t")


def is_structural_only(text: str) -> bool:
    """True when *text* is purely markdown structure (horizontal rule,
    separator, empty).  Requires at least three non-whitespace structural
    characters so single-dash or asterisk content doesn't get swallowed."""
    s = text.strip()
    if not s:
        return True
    if not all(c in _STRUCTURAL_CHARS for c in s):
        return False
    # Count actual rule characters (drop whitespace) — needs >=3 to be
    # a horizontal rule rather than a stray hyphen.
    dense = "".join(c for c in s if c not in " \t")
    return len(dense) >= 3


# Label display transformations.  Source text often uses conventions that
# read well in files (ISO dates, em-dash separators, markdown emphasis
# markers) but sound stilted when squeezed onto a small AboutNode.  These
# helpers rewrite only what's displayed — the source text stays untouched.
_ISO_DATE_RE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')

# ASCII tree / box-drawing chars — Unicode Box Drawing block (U+2500..U+257F).
# These show up in source markdown as visual scaffolding inside <pre> blocks
# (the markdown→HTML render converts them to 📁/📄 emojis upstream); in the
# rare event one survives into a title or label slot, strip it so the spawned
# node reads as content, not as a stray tree-branch fragment.
_BOX_DRAWING_RE = re.compile(r'\s*[─-╿]+\s*')

_MONTH_NAMES = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)


def _ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th, 11th, 21st, …"""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def prettify_label(text: str) -> str:
    """Rewrite source conventions that read awkwardly on a compressed
    AboutNode label:

    - ISO dates (``2026-04-15``) → ``April 15th 2026``
    - em-dash separators (``A — B``) → colons (``A: B``)
    - ``**bold**`` and ``*italic*`` markers stripped — the wrapped word
      stays; on a compressed AboutNode the text's own colon / em-dash /
      cadence carries the emphasis without needing inline font-weight or
      slant.  Bold pairs are stripped first, then any remaining lone
      asterisks (single-``*`` italic).
    - box-drawing chars (``├└│─`` and the rest of the U+2500 block)
      stripped — defensive backstop in case ASCII tree scaffolding leaks
      from a ``<pre>`` block into a title slot.
    - backticks stripped — ``` `ident` `` reads as visual clutter on a
      plain-text surface.
    - trailing colon stripped — on an AboutNode the colon dangles
      because the node is already the label visually.  Mid-string
      colons (ratios, times) are untouched.

    Surrounding prose is preserved verbatim.  Invalid dates
    (month > 12, day > 31) pass through unchanged.  Em-dashes without
    surrounding spaces (compound words like ``word—word``) are untouched
    — only the separator use converts."""
    def _date_repl(m):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)
        return f"{_MONTH_NAMES[mo - 1]} {_ordinal(d)} {y}"
    text = _ISO_DATE_RE.sub(_date_repl, text)
    # Em-dash with surrounding spaces → colon + space.  Catches the
    # "date — label" / "term — definition" pattern without touching
    # compound-word em-dashes (which have no surrounding spaces).
    text = text.replace(" — ", ": ")
    # Strip markdown bold markers, then any remaining lone asterisks
    # (single-``*`` italic).  Order matters only for readability — both
    # `replace` passes globally remove the char regardless of pairing.
    text = text.replace("**", "")
    text = text.replace("*", "")
    # Strip ASCII tree / box-drawing chars — defensive backstop for the
    # rare case where source scaffolding lands in a title slot.  Replace
    # with a single space so a mid-word run (``Header ├── continuation``)
    # collapses to one space rather than fusing the words together; the
    # closing ``strip()`` removes any space introduced at the edges.
    text = _BOX_DRAWING_RE.sub(" ", text)
    # Strip inline-code backticks.
    text = text.replace("`", "")
    # Strip leading/trailing whitespace, then a trailing colon.
    text = text.strip()
    if text.endswith(':'):
        text = text[:-1].strip()
    return text
