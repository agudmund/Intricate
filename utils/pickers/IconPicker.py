#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - IconPicker.py emoji icon bank
-Curated list of emoji icons used for node accent decoration for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random as _random

emojiIcons = [
    "😀", "😁", "😃", "😉", "😊", "😋", "😎", "😍", "😘", "🥰",
    "😗", "🥲", "😚", "🙂", "🤩", "🤔", "🧸", "😮", "🫤", "😒",
    "😥", "😏", "😲", "😬", "😇", "🙂‍↔", "🥺", "😟", "🫢", "🫡",
    "🤨", "😐", "😌", "😔", "🫣",
]


def randomling() -> str:
    """Return a random emoji from the curated icon bank."""
    return _random.choice(emojiIcons)


def sampleling(n: int) -> list[str]:
    """Return *n* unique emojis sampled without replacement (capped at bank size)."""
    return _random.sample(emojiIcons, min(n, len(emojiIcons)))
