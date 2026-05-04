#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate icon pipeline - paths.py canonical project paths
-and they learnt to whisper to each other across the same source dirs for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Why this is its own module
# ──────────────────────────
# Author scripts originally used a mix of conventions: some had
# `os.path.dirname(__file__)`, some had `Path(__file__).resolve().parent`,
# some used bare relative paths like `"icons/Push.png"` assuming the
# script ran from project root.  When the scripts moved into
# icons/_pipeline/scripts/, the __file__-based paths suddenly pointed
# two directories deeper and several scripts stopped finding their
# source assets.
#
# Centralising on REPO_ROOT (resolved once via __file__ here) means
# every script that imports from this toolkit gets a stable anchor
# regardless of where the script itself lives within the project tree.

from pathlib import Path

# This file lives at icons/_pipeline/paths.py, so REPO_ROOT is two
# parents up.  Resolve to absolute so callers can use it from any cwd.
REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
ICONS_DIR  = REPO_ROOT / "icons"
IMAGES_DIR = REPO_ROOT / "Images"
