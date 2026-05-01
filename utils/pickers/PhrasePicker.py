#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/pickers/PhrasePicker.py phrase bank
-The last of the phrase picker held a quiet collection of small uplifting words, ready to lend one whenever a name was needed, For Enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random as _random

motivationalMessages = [
    "Accurate",
    "All Glory",
    "Beautiful",
    "Becoming Yours",
    "Bloom",
    "Boundless Joy",
    "Bright Tomorrow",
    "Clay",
    "Clear Vision",
    "Delicate",
    "Elegant",
    "Endless Potential",
    "Evolve",
    "Fresh Start",
    "Gentle",
    "Golden Hour",
    "Good",
    "Grace",
    "Growth",
    "Infinite Wisdom",
    "Inner Peace",
    "Intentional",
    "Intricate",
    "Irresistible",
    "Kinetic",
    "New Thought",
    "Omnious",
    "Onward",
    "Practical and pleasurable",
    "Pure Light",
    "Soft",
    "Sweet",
    "Tiny little extra sprinkles of joy",
    "Unfold",
]


def randomling() -> str:
    """Return a random phrase from the curated phrase bank."""
    return _random.choice(motivationalMessages)


def sampleling(n: int) -> list[str]:
    """Return *n* unique phrases sampled without replacement (capped at bank size)."""
    return _random.sample(motivationalMessages, min(n, len(motivationalMessages)))
