#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/pickers/ColorPicker.py node tint palette facade
-A quiet window onto color_registry.toml — reads live, reports needs for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random as _random

# The palette itself lives in color_registry.toml (via utils.persistence.
# color_registry).  This module is the facade existing call sites — BaseNode's
# tint toggle, AboutNode's picker, ClaudeNode's random pick — still talk to.
# Keeping the old surface stable means nothing further up the stack had to
# learn about the registry.
from utils.persistence import color_registry as _registry


def get(index: int) -> str:
    """Return the color at *index*, wrapping around if out of range."""
    colors = _registry.get_all()
    if not colors:
        # Registry briefly empty during a live Settlers write — fall back
        # to the seed so callers never hit a divide-by-zero.
        colors = list(_registry._SEED_COLORS)
    return colors[index % len(colors)]


def random() -> str:
    """Return a random color from the palette."""
    colors = _registry.get_all() or list(_registry._SEED_COLORS)
    return _random.choice(colors)


def sample(n: int) -> list[str]:
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
