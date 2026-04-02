#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/helpers.py common helper utilities
-Shared helpers that keep the codebase consistent and tidy for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("helpers")


def ensure_dir(path: str | Path) -> bool:
    """Create a directory (and parents) if it doesn't already exist.

    Returns True if the directory is usable after the call, False on failure.
    """
    path = Path(path)
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"🌱 Created directory: {path}")
        else:
            logger.info(f"✓ Directory already exists: {path}")
        return True
    except OSError as e:
        logger.warning(f"⚠ Failed to create directory: {path} — {e}")
        return False
