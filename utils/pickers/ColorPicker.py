#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/ColorPicker.py ColorPicker utility
-A small curated palette sampled from Paradisic Fields, ready to tint any node for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random as _random

# Curated from the Paradisic Fields project palette — warm reds, earthy neutrals, muted greens.
_COLORS = [
    "#2a2f3a",  # dusk slate
    "#b05f5f",  # old brick
    "#4a3a5a",  # plum shadow
    "#1e1e1e",  # charcoal
]


def get(index: int) -> str:
    """Return the color at *index*, wrapping around if out of range."""
    return _COLORS[index % len(_COLORS)]


def random() -> str:
    """Return a random color from the palette."""
    return _random.choice(_COLORS)


def sample(n: int) -> list[str]:
    """Return *n* unique colors sampled without replacement (capped at palette size)."""
    return _random.sample(_COLORS, min(n, len(_COLORS)))


def all_colors() -> list[str]:
    """Return the full palette as a list."""
    return list(_COLORS)
