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

# Launcher-based map: any target QFileIconProvider can resolve → cached
# filename.  Used for apps that don't register a distinct file extension —
# our own braincell tools (via Desktop .lnk), Claude Desktop (MSIX, via the
# shell:AppsFolder virtual path), Claude Code CLI (direct exe), anything
# else that has a launcher identity but no file-type claim.
#
# Key resolution:
#   "~/..."      → Path.expanduser()
#   "shell:..."  → passed through for MSIX AppsFolder targets
#   absolute     → used as-is
#
# Extraction is once-per-missing; these apps don't re-skin often enough to
# justify a staleness check.  Delete the cached .ico to force a refresh.
_LAUNCHER_ICON_MAP: dict[str, str] = {
    # Our own braincell-family apps via their Desktop shortcuts
    "~/Desktop/Intricate/Intricate.lnk":             "intricate_app.ico",
    "~/Desktop/The Settlers/The Settlers.lnk":       "the_settlers_app.ico",
    # Anthropic's Claude Desktop — MSIX app, identified by its AppUserModelID
    "shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude": "claude_desktop.ico",
    # Claude Code CLI — direct executable in the user's local bin
    "~/.local/bin/claude.exe":                       "claude_cli.ico",
}


def _resolve_launcher_target(key: str) -> str:
    """Expand ~ for filesystem paths; pass shell: paths through unchanged.
    Qt's QFileIconProvider accepts both forms."""
    if key.startswith("shell:"):
        return key
    return str(Path(key).expanduser())

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

def _extract_via_qt(target: QFileInfo, dest: Path, label: str) -> bool:
    """Shared extraction core — takes a QFileInfo pointing at either a
    dummy path with a known extension or a real file path (e.g. a .lnk
    shortcut), pulls the icon via QFileIconProvider, and saves it as a
    multi-resolution .ico at *dest*.

    QFileIconProvider is the cross-platform Qt wrapper around the OS
    file-type icon lookup; on Windows it routes through SHGetFileInfoW
    under the hood, returning whatever Explorer would render.  No
    subprocess, no brand-pack download — the app's own installer put
    the icon on this machine already; we just ask.

    *label* is a human-readable tag for log lines (the extension or the
    shortcut path), surfaced only on warning/info messages.
    """
    from PIL import Image
    from io import BytesIO

    provider = QFileIconProvider()
    icon = provider.icon(target)
    if icon.isNull():
        _log.warning(f"[app_icons] no OS icon for {label}")
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
        _log.warning(f"[app_icons] no pixmaps produced for {label}")
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
        _log.info(f"[app_icons] cached {label} → {dest.name}")
        return True
    except OSError as e:
        _log.warning(f"[app_icons] save failed for {label}: {e}")
        return False


def extract_app_icon(extension: str, dest: Path) -> bool:
    """Extract the default-handler icon for *extension* via the OS lookup.
    The dummy path doesn't need to exist — Qt only consults the extension."""
    return _extract_via_qt(QFileInfo(f"dummy{extension}"), dest, extension)


def extract_launcher_icon(target: str, dest: Path) -> bool:
    """Extract the icon displayed for a launcher target — a filesystem
    path (.lnk, .exe) or a shell: URI (MSIX AppsFolder entries).

    Filesystem targets must exist; shell: targets are passed through and
    resolved by Windows at extraction time.  Failure is non-fatal — the
    caller keeps whatever cached .ico is already in place.
    """
    if target.startswith("shell:"):
        # Pass-through; Windows resolves the AppsFolder virtual path
        return _extract_via_qt(QFileInfo(target), dest, target)
    path = Path(target)
    if not path.exists():
        _log.debug(f"[app_icons] launcher not present, skipping: {path}")
        return False
    return _extract_via_qt(QFileInfo(str(path)), dest, path.name)


# ─────────────────────────────────────────────────────────────────────────────
# BOOT — ensure cached icons exist and are current
# ─────────────────────────────────────────────────────────────────────────────

def ensure_app_icons() -> None:
    """Check every registered extension and launcher; extract or refresh as needed.

    Call after QApplication exists (QFileIconProvider needs it).  Cost is
    negligible on subsequent boots — if nothing is stale, just a handful
    of stat() calls.  Freshly-installed machine's first boot does the
    extraction work, which takes milliseconds per icon.
    """
    d = icons_dir()
    # Extension-based: Adobe apps, third-party tools we don't own
    for ext, filename in _APP_ICON_MAP.items():
        cached = d / filename
        if _is_stale(cached, ext):
            extract_app_icon(ext, cached)
    # Launcher-based: our own apps, Claude Desktop (MSIX), Claude CLI
    for key, filename in _LAUNCHER_ICON_MAP.items():
        cached = d / filename
        if not cached.exists():
            extract_launcher_icon(_resolve_launcher_target(key), cached)
