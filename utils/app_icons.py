#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/app_icons.py OS-registered app icon extractor
-and they learnt to whisper to each other across Windows' shell handler registry for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, QBuffer, QIODevice
from PySide6.QtWidgets import QFileIconProvider

from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("app_icons")


# Extension → cached filename under ./icons/.  Add a new entry here when a
# new Adobe (or any other app-registered) icon is needed in the sidebar;
# the cache fills itself at next app boot.  Icons live under the repo's
# icons/ directory alongside the handmade ones, but are regenerated from
# the OS on demand so they stay current with whatever app version Windows
# has registered as the default handler.
_APP_ICON_MAP: dict[str, str] = {
    ".indd":   "indesign_app.ico",
    # Ready to populate as more Adobe launchers arrive:
    # ".psd":    "photoshop_app.ico",
    # ".ai":     "illustrator_app.ico",
    # ".aep":    "aftereffects_app.ico",
    # ".prproj": "premiere_app.ico",
}

# Sizes baked into each multi-resolution .ico.  Qt renders each size
# individually via Windows' shell icon cache so small sizes benefit from
# the hand-tuned variants Windows ships, when available.
_ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

def icons_dir() -> Path:
    """Resolve ./icons/ next to main.py — three parents up from this file."""
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "icons"


# ─────────────────────────────────────────────────────────────────────────────
# STALENESS — did Adobe (or whoever) ship a new version since we cached?
# ─────────────────────────────────────────────────────────────────────────────

def _default_handler_exe(extension: str) -> Path | None:
    """Walk the Windows registry to find the exe registered as the default
    handler for *extension*. Returns None if no handler is registered or the
    registry walk fails.  Used purely for mtime comparison against the
    cached icon — an upstream upgrade ticks the exe's mtime, we notice."""
    try:
        import winreg
    except ImportError:
        return None
    import shlex
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, extension) as k:
            progid, _ = winreg.QueryValueEx(k, "")
        if not progid:
            return None
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, rf"{progid}\shell\open\command"
        ) as k:
            cmd, _ = winreg.QueryValueEx(k, "")
    except (FileNotFoundError, OSError):
        return None
    # Command line is typically  "C:\Path\App.exe" "%1"
    # shlex with posix=False preserves Windows quoting
    try:
        tokens = shlex.split(cmd, posix=False)
    except ValueError:
        return None
    if not tokens:
        return None
    exe = Path(tokens[0].strip('"'))
    return exe if exe.exists() else None


def _is_stale(cached: Path, extension: str) -> bool:
    """True if *cached* should be re-extracted.  Missing-file is stale; an
    extant cache compares its mtime to the default handler's exe mtime so
    an Adobe update at any point since the last extraction triggers a
    refresh automatically.  If the exe can't be resolved, trust the cache."""
    if not cached.exists():
        return True
    exe = _default_handler_exe(extension)
    if exe is None:
        return False
    try:
        return exe.stat().st_mtime > cached.stat().st_mtime
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_app_icon(extension: str, dest: Path) -> bool:
    """Ask Windows what icon is registered for *extension*, collect it at
    every size in _ICO_SIZES via Qt's QFileIconProvider, and save the pack
    as a multi-resolution .ico at *dest*.

    QFileIconProvider is the cross-platform Qt wrapper around the OS file-
    type icon lookup; on Windows it routes through SHGetFileInfoW under
    the hood, returning whatever Explorer would render for a file with
    that extension.  No subprocess, no brand-pack download — the app's
    own installer put the icons on this machine already; we just ask.

    Returns True on success. Per-failure warnings go to the logger so a
    broken lookup doesn't cascade into a launch-blocking error.
    """
    from PIL import Image
    from io import BytesIO

    provider = QFileIconProvider()
    # The path doesn't need to exist — Qt only consults the extension.
    icon = provider.icon(QFileInfo(f"dummy{extension}"))
    if icon.isNull():
        _log.warning(f"[app_icons] no OS icon registered for {extension}")
        return False

    # Convert each size via PNG roundtrip — cleanest QPixmap→PIL path,
    # no manual buffer-layout math that tends to miscount strides.
    frames: list[Image.Image] = []
    for size in sorted(_ICO_SIZES, reverse=True):   # largest first
        pixmap = icon.pixmap(QSize(size, size))
        if pixmap.isNull():
            continue
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pixmap.save(buf, "PNG")
        png_bytes = bytes(buf.data().data())
        frames.append(Image.open(BytesIO(png_bytes)).convert("RGBA"))

    if not frames:
        _log.warning(f"[app_icons] no pixmaps produced for {extension}")
        return False

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # PIL's ICO writer packs the primary image plus append_images into
        # one multi-resolution file.  Each frame is preserved at its
        # native size rather than being downsampled from a single source.
        frames[0].save(
            str(dest),
            format="ICO",
            sizes=[(f.width, f.height) for f in frames],
            append_images=frames[1:],
        )
        _log.info(f"[app_icons] cached {extension} → {dest.name}")
        return True
    except OSError as e:
        _log.warning(f"[app_icons] save failed for {extension}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# BOOT — ensure cached icons exist and are current
# ─────────────────────────────────────────────────────────────────────────────

def ensure_app_icons() -> None:
    """Check every registered extension; extract or refresh as needed.

    Call after QApplication exists (QFileIconProvider needs it).  Cost is
    negligible on subsequent boots — if nothing is stale, just a handful
    of stat() calls.  Freshly-installed machine's first boot does the
    extraction work, which takes milliseconds per icon.
    """
    d = icons_dir()
    for ext, filename in _APP_ICON_MAP.items():
        cached = d / filename
        if _is_stale(cached, ext):
            extract_app_icon(ext, cached)
