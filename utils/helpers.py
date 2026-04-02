#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/helpers.py common helper utilities
-Shared helpers that keep the codebase consistent and tidy for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import shutil
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("helpers")


# ── __init__.py template ─────────────────────────────────────────────────────
_INIT_TEMPLATE = (
    '#!/usr/bin/env python3\n'
    '# -*- coding: utf-8 -*-\n'
    '"""\n'
    '-Intricate nodal playground - {path}/__init__.py package initializer\n'
    '-{name} package initializer for enjoying\n'
    '-Built using a single shared braincell by Yours Truly and various Intelligences\n'
    '"""\n'
)


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


def ensure_init(path: str | Path, project_root: str | Path | None = None) -> bool:
    """Create __init__.py with the standard header if missing.

    Args:
        path:         The directory that should contain __init__.py.
        project_root: Optional root for deriving the relative path in the header.
                      Falls back to using the directory name alone.

    Returns True if __init__.py exists after the call, False on failure.
    """
    path = Path(path)
    init_file = path / "__init__.py"
    if init_file.exists():
        logger.info(f"✓ __init__.py already in {path}")
        return True
    try:
        rel  = path.relative_to(project_root) if project_root else Path(path.name)
        name = rel.parts[-1].capitalize() if rel.parts else path.name.capitalize()
        init_file.write_text(
            _INIT_TEMPLATE.format(path=rel.as_posix(), name=name),
            encoding="utf-8",
        )
        logger.info(f"🌱 Created __init__.py in {path}")
        return True
    except OSError as e:
        logger.warning(f"⚠ Failed to create __init__.py in {path} — {e}")
        return False


def ensure_init_tree(root: str | Path) -> int:
    """Walk a project tree and create missing __init__.py in Python package folders.

    A subfolder is treated as a library package when it contains .py files
    but no main.py.  Folders with main.py are standalone entry points and
    are left alone.

    Returns the number of __init__.py files created.
    """
    root = Path(root)
    skip = {".git", "__pycache__"}
    created = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        py_files = [f for f in filenames if f.endswith(".py")]
        if not py_files or "main.py" in py_files or "__init__.py" in py_files:
            continue
        if ensure_init(dirpath, project_root=root):
            created += 1
    return created


def clean_pycache(root: str | Path | None = None) -> int:
    """Remove all __pycache__ folders and .pyc files under root.

    Args:
        root: Directory to clean. Defaults to the project root
              (parent of utils/).

    Returns the number of __pycache__ directories removed.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    root = Path(root)
    cleaned = 0
    try:
        for item in root.rglob("__pycache__"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                logger.info(f"🧹 Removed: {item}")
                cleaned += 1
        for item in root.rglob("*.pyc"):
            item.unlink(missing_ok=True)
    except Exception:
        pass
    return cleaned
