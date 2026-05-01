#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/pickers/IconPicker.py emoji icon bank
-The last of the icon picker kept its small bouquet of warm faces curated by hand, ready for any node that wanted an accent, For Enjoying
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
