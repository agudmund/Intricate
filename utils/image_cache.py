#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/image_cache.py proprietary image cache
-SHA-256 addressed PNG cache so images survive source file deletion for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import hashlib
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QImage

from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("cache")


_cache_root: Path | None = None


def set_cache_root(project_data_dir: Path) -> None:
    """Set the cache root to the active project's data directory.
    Called by main_window when a project is selected/loaded.
    """
    global _cache_root
    _cache_root = project_data_dir / "cache"
    _cache_root.mkdir(parents=True, exist_ok=True)


def cache_dir() -> Path:
    """Return (and create) the image cache directory.
    Falls back to Intricate's own Documents/data/cache if no project root is set.
    """
    if _cache_root is not None:
        _cache_root.mkdir(parents=True, exist_ok=True)
        return _cache_root
    d = Path(__file__).resolve().parent.parent / "Documents" / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    """Encode a QPixmap to raw PNG bytes."""
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    return bytes(buf.data().data())


def cache_pixmap(pixmap: QPixmap) -> str:
    """Write a pixmap to the cache as PNG. Returns the SHA-256 hash key.

    If the file already exists (same content hash), the write is skipped —
    automatic deduplication. Returns empty string if pixmap is null/empty.
    """
    if pixmap is None or pixmap.isNull():
        return ""
    raw = _pixmap_to_png_bytes(pixmap)
    if not raw:
        return ""
    key = hashlib.sha256(raw).hexdigest()
    path = cache_dir() / f"{key}.png"
    if not path.exists():
        path.write_bytes(raw)
        logger.debug(f"[cache] wrote {key[:12]}… ({len(raw):,} bytes)")
    return key


def load_cached(key: str) -> QPixmap | None:
    """Load a pixmap from the cache by its hash key. Returns None if missing."""
    if not key:
        return None
    path = cache_dir() / f"{key}.png"
    if not path.exists():
        return None
    img = QImage(str(path))
    if img.isNull():
        return None
    return QPixmap.fromImage(img)


def gc_cache(live_keys: set[str]) -> int:
    """Remove cache files not referenced by any live node.

    Returns the number of files removed.
    """
    removed = 0
    for path in cache_dir().glob("*.png"):
        key = path.stem
        if key not in live_keys:
            try:
                path.unlink()
                logger.debug(f"[cache] gc removed {key[:12]}…")
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info(f"[cache] gc cleaned {removed} orphaned file(s)")
    return removed
