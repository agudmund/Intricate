#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/pickers/ColorPicker.py node tint palette facade
-The last of the color picker spoke for a palette it never owned, content to ask the registry every time and trust the answer, For Enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random as _random

# Thin facade onto color_registry.toml — palette lives in the TOML
# (loaded via utils.persistence.color_registry); this module exposes
# the get / random / sample / register surface so callers above didn't
# need to learn about the registry when the data moved out.
# Current callers: BaseNode (tint cycling) and ClaudeNode (chain colours).
from utils.persistence import color_registry as _registry


def get(index: int) -> str:
    """Return the color at *index*, wrapping around if out of range."""
    colors = _registry.get_all()
    if not colors:
        # Registry briefly empty during a live Settlers write — fall back
        # to the seed so callers never hit a divide-by-zero.
        colors = list(_registry._SEED_COLORS)
    return colors[index % len(colors)]


def randomling() -> str:
    """Return a random color from the palette."""
    colors = _registry.get_all() or list(_registry._SEED_COLORS)
    return _random.choice(colors)


def sampleling(n: int) -> list[str]:
    """Return *n* unique colors sampled without replacement (capped at palette size)."""
    colors = _registry.get_all() or list(_registry._SEED_COLORS)
    return _random.sample(colors, min(n, len(colors)))


def all_colors() -> list[str]:
    """Return the full palette as a list."""
    return _registry.get_all()


def register(hex_color: str) -> int:
    """Ensure *hex_color* is in the palette and persist.  Returns its index.

    This is the write path Intricate uses to communicate needs to the
    control board — the registry writes color_registry.toml, The Settlers
    watches and picks up the new color in its Color Picker category.
    """
    return _registry.register(hex_color)


def reset_to_defaults() -> None:
    """Restore the palette to the curated seed, dropping any runtime additions."""
    _registry.set_all(_registry._SEED_COLORS)
