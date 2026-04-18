#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/media_cache.py proprietary media cache
-SHA-256 addressed byte-preserving cache shared by image and video nodes for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import hashlib
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QImage

from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("cache")


# Keys are "<sha256>.<ext>" — self-describing filenames preserving source format.
# Legacy bare-hash keys (no extension) resolve to .png via the fallback in load_cached.

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
    # This file lives at utils/persistence/media_cache.py — repo root is
    # three parents up (2026-04-18 utils regrouping).
    d = Path(__file__).resolve().parent.parent.parent / "Documents" / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    """Encode a QPixmap to raw PNG bytes."""
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    return bytes(buf.data().data())


def _resolve_cache_path(key: str) -> Path | None:
    """Map a cache_key to an on-disk path. Handles both dotted and legacy bare keys."""
    if not key:
        return None
    d = cache_dir()
    if "." in key:
        p = d / key
        return p if p.exists() else None
    # Legacy: bare hash → assume .png (the only format the v0.1 cache produced)
    p = d / f"{key}.png"
    return p if p.exists() else None


def cache_source_bytes(raw: bytes, ext: str) -> str:
    """Cache raw source file bytes verbatim. Returns '<sha256>.<ext>' key.

    Preserves all embedded metadata — EXIF, XMP, ICC profiles, tEXt stamps —
    because the cached file is a byte-for-byte copy of the source.
    Empty input returns empty string.
    """
    if not raw:
        return ""
    ext = ext.lstrip(".").lower() or "bin"
    key = f"{hashlib.sha256(raw).hexdigest()}.{ext}"
    path = cache_dir() / key
    if not path.exists():
        path.write_bytes(raw)
        logger.debug(f"[cache] wrote {key[:12]}… .{ext} ({len(raw):,} bytes)")
    return key


def cache_source_file(src_path: Path) -> str:
    """Stream-hash and copy a source file into the cache. Returns '<sha256>.<ext>'.

    For large files (video) where reading the whole source into memory is wasteful.
    Hashes and writes in 1 MiB chunks in a single pass. If the hash already exists
    in the cache, skips the copy. Empty or missing source returns empty string.
    """
    if not src_path or not src_path.exists():
        return ""
    ext = src_path.suffix.lstrip(".").lower() or "bin"

    # First pass: streaming SHA. We accept one extra read over the source so
    # the common "already cached" case costs hash-only, no second copy.
    h = hashlib.sha256()
    try:
        with open(src_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    key = f"{h.hexdigest()}.{ext}"
    dst = cache_dir() / key
    if dst.exists():
        return key

    # Second pass: stream-copy. shutil.copyfile is the fastest portable
    # copy on Windows (uses CopyFileEx under the hood in newer Pythons).
    import shutil
    try:
        shutil.copyfile(src_path, dst)
        logger.debug(f"[cache] wrote {key[:12]}… .{ext} ({src_path.stat().st_size:,} bytes, stream)")
    except OSError:
        return ""
    return key


def cache_pixmap(pixmap: QPixmap) -> str:
    """Fallback for pasted or generated images with no source file on disk.
    PNG-encodes the pixmap and caches it. Returns '<sha256>.png' key.
    Prefer cache_source_bytes when the original file is available.
    """
    if pixmap is None or pixmap.isNull():
        return ""
    raw = _pixmap_to_png_bytes(pixmap)
    return cache_source_bytes(raw, "png")


def load_cached(key: str) -> QPixmap | None:
    """Load a pixmap from the cache by its key. Accepts dotted or legacy bare keys."""
    path = _resolve_cache_path(key)
    if path is None:
        return None
    img = QImage(str(path))
    if img.isNull():
        return None
    return QPixmap.fromImage(img)


def cached_path(key: str) -> Path | None:
    """Return the absolute Path to the cached file for a key, or None if missing.

    Used by QMediaPlayer and any other consumer that loads media by filesystem
    path rather than in-memory bytes. Accepts both dotted and legacy bare keys.
    """
    return _resolve_cache_path(key)


def cached_bytes(key: str) -> bytes | None:
    """Return the raw cached file bytes for a key, or None if missing.
    Useful for hashing/verification without going through QPixmap decode.
    """
    path = _resolve_cache_path(key)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def hash_file(path: Path) -> str | None:
    """SHA-256 a file on disk in streaming chunks. Returns None on read error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def key_hash(key: str) -> str:
    """Return just the SHA-256 hash portion of a key (handles both formats)."""
    return key.split(".", 1)[0] if key else ""


def gc_cache(live_keys: set[str]) -> int:
    """Remove cache files not referenced by any live node.

    Matches files by either full dotted name (e.g. 'abc….jpg') or bare hash
    (legacy keys). Returns the number of files removed.
    """
    # Normalise to match either form on disk
    live_names = set(live_keys)
    live_stems = {key_hash(k) for k in live_keys}

    removed = 0
    for path in cache_dir().iterdir():
        if not path.is_file():
            continue
        if path.name in live_names or path.stem in live_stems:
            continue
        try:
            path.unlink()
            logger.debug(f"[cache] gc removed {path.name[:16]}…")
            removed += 1
        except OSError:
            pass
    if removed:
        logger.info(f"[cache] gc cleaned {removed} orphaned file(s)")
    return removed
