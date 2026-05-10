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

from shared_braincell.logger import setup_logger

_log = setup_logger("app_icons")


# Extension → cached filename relative to ./icons/.  Add a new entry here
# when a new Adobe (or any other app-registered) icon is needed in the
# sidebar; the cache fills itself at next app boot.
#
# Filenames are PREFIXED with the Tertiary/ subfolder so third-party brand
# assets stay separated from Intricate's proprietary icons.  See the Icon
# Pipeline doc's "Proprietary vs Tertiary" section — the rule is that we
# never alter another company's branding, and the directory split makes
# the boundary visible at a glance in the asset folder.
#
# Regenerated from the OS on demand so they stay current with whatever
# app version Windows has registered as the default handler.
_APP_ICON_MAP: dict[str, str] = {
    ".indd":   "Tertiary/indesign_app.ico",
    ".prproj": "Tertiary/premiere_app.ico",
    # Ready to populate as more Adobe launchers arrive:
    # ".psd":    "Tertiary/photoshop_app.ico",
    # ".ai":     "Tertiary/illustrator_app.ico",
    # ".aep":    "Tertiary/aftereffects_app.ico",
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
    # Our own braincell-family apps via their Desktop shortcuts — these
    # are PROPRIETARY, cached at icons/ root.
    #
    # Principle: this map is the **external-change detector** — it picks
    # up icon updates that happen *outside* Intricate's scope (a sibling
    # app rebuilding, an MSIX update, a third-party reinstall).  Icons we
    # author and ship ourselves don't belong here, because the chain
    # already flows IN-from our branding sources; running our own .lnk
    # through Windows shell extraction would be circular and would let
    # an OS-side cache state override our canonical file.
    #
    # Hence: Intricate itself is excluded — its source of truth is
    # icons/Stickers/Intricate.ico, which build.py embeds into the .exe and the
    # .lnk inherits.  Other family apps remain here for now while their
    # .lnk is still the only handle on their identity from this side.
    "~/Desktop/The Settlers/The Settlers.lnk":       "the_settlers_app.ico",
    # Anthropic's Claude Desktop — MSIX app, identified by its AppUserModelID.
    # TERTIARY (third-party brand) — cached under icons/Tertiary/.
    "shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude": "Tertiary/claude_desktop.ico",
    # Claude Code CLI — direct executable in the user's local bin.
    # TERTIARY — cached under icons/Tertiary/.
    "~/.local/bin/claude.exe":                       "Tertiary/claude_cli.ico",
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


def _data_dir() -> Path:
    """Resolve ./Documents/Data/ — the runtime cache home.

    Mirrors icons_dir()'s frozen-vs-source split.  Used by the launcher
    pipeline sentinel so the cache-version marker lives next to other
    runtime state (joy_buckets.txt, joy_state.json, companion.json)
    instead of cluttering the icons/ folder, which is reserved for
    actual icon assets.
    """
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "Documents" / "Data"


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


def _resolve_lnk_icon_source(lnk_path: Path) -> tuple[Path, int] | None:
    """Resolve a .lnk shortcut to the source the icon should come from.

    Two sources of truth, consulted in order:

    1. **GetIconLocation** — explicit override the shortcut creator set
       via right-click → Properties → Change Icon.  If non-empty, this
       is exactly what Windows displays in Explorer (minus the overlay
       arrow), so it's the authoritative answer.  Common case for our
       own apps where the launcher targets pythonw.exe but a project-
       local .ico provides the visual identity.

    2. **GetPath** (fallback) — the launcher's target executable.  Used
       when no custom icon override is set; the shell would derive the
       icon from the target's resource section.

    Either way the shell overlay arrow is sidestepped because we're
    extracting from the underlying icon file, not asking the shell to
    render an .lnk.  Returns (path, index) — index is the icon resource
    number for .exe/.dll; meaningless for .ico files but harmless to
    pass through.

    Returns None if pywin32 isn't available, IShellLink load fails, or
    neither source resolves to an existing file.  Caller falls back to
    extracting from the .lnk directly in that case (functional
    regression: arrow returns, no crash).
    """
    try:
        import pythoncom
        from win32com.shell import shell
    except ImportError:
        _log.debug("[app_icons] pywin32 unavailable; .lnk overlay arrow will persist")
        return None
    try:
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink,
        )
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(lnk_path))
        # First preference: explicit IconLocation override
        icon_raw, icon_idx = link.GetIconLocation()
        if icon_raw:
            from os.path import expandvars
            icon_path = Path(expandvars(icon_raw))
            if icon_path.exists():
                return (icon_path, icon_idx)
            _log.debug(f"[app_icons] .lnk IconLocation missing on disk: {icon_path}")
        # Fallback: target executable's default icon
        target, _ = link.GetPath(shell.SLGP_RAWPATH)
        if target:
            target_path = Path(target)
            if target_path.exists():
                return (target_path, 0)
            _log.debug(f"[app_icons] .lnk target missing on disk: {target_path}")
        return None
    except Exception as e:   # COM failures surface as a wide range of types
        _log.debug(f"[app_icons] .lnk resolve failed for {lnk_path.name}: {e}")
        return None


def _copy_ico(src: Path, dest: Path, label: str) -> bool:
    """Copy an .ico file straight to dest — best fidelity, no rasterize/repack.

    Used when a .lnk's IconLocation already points at an .ico file (the
    common case for our own apps).  Skipping the QPixmap roundtrip
    preserves whatever resolution layers the original .ico shipped with,
    including the hand-tuned 16/24/32 px versions Windows uses for tiny
    sidebar buttons.
    """
    import shutil
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        _log.info(f"[app_icons] copied {label} from {src.name}")
        return True
    except OSError as e:
        _log.warning(f"[app_icons] copy failed for {label}: {e}")
        return False


def extract_launcher_icon(target: str, dest: Path) -> bool:
    """Extract the icon displayed for a launcher target — a filesystem
    path (.lnk, .exe) or a shell: URI (MSIX AppsFolder entries).

    Filesystem targets must exist; shell: targets are passed through and
    resolved by Windows at extraction time.  .lnk targets are resolved
    via IShellLink so the shell's shortcut overlay arrow doesn't end up
    baked into the cached icon, and the .lnk's own custom IconLocation
    (if set) is honoured rather than being shadowed by the target exe's
    default icon.  Failure is non-fatal — the caller keeps whatever
    cached .ico is already in place.
    """
    if target.startswith("shell:"):
        # Pass-through; Windows resolves the AppsFolder virtual path
        return _extract_via_qt(QFileInfo(target), dest, target)
    path = Path(target)
    if not path.exists():
        _log.debug(f"[app_icons] launcher not present, skipping: {path}")
        return False
    if path.suffix.lower() == ".lnk":
        resolved = _resolve_lnk_icon_source(path)
        if resolved is not None:
            src_path, _src_idx = resolved
            label = f"{path.name} → {src_path.name}"
            # If the source is itself an .ico, copy verbatim — preserves
            # all resolution layers without QPixmap roundtrip.
            if src_path.suffix.lower() == ".ico":
                return _copy_ico(src_path, dest, label)
            # .exe/.dll source: fall through to Qt extraction.  Note that
            # QFileIconProvider always returns the file's default (index 0)
            # icon; if a non-zero icon index ever appears in the wild we'd
            # need ExtractIconExW to honour it.
            return _extract_via_qt(QFileInfo(str(src_path)), dest, label)
        # Fall through: .lnk extraction with overlay arrow as last resort
    return _extract_via_qt(QFileInfo(str(path)), dest, path.name)


# ─────────────────────────────────────────────────────────────────────────────
# BOOT — ensure cached icons exist and are current
# ─────────────────────────────────────────────────────────────────────────────

# Bumped whenever the launcher extraction pipeline changes in a way that
# requires the .lnk-sourced cache entries to be regenerated.  Sentinel
# file lives in icons/ alongside the .icos themselves; if missing, the
# affected cached icons are deleted so ensure_app_icons re-extracts them.
#  v2 — resolve .lnk → target exe to drop the shell's overlay arrow
#  v3 — consult .lnk IconLocation first; honour custom-icon overrides
#       (target was pythonw.exe → ignored Intricate's project-local .ico)
_LAUNCHER_PIPELINE_SENTINEL = ".launcher_icon_v3"


def _self_heal_lnk_cache(d: Path) -> None:
    """One-shot invalidation of .lnk-sourced cached icons after a pipeline bump.

    Runs once per pipeline version: if the sentinel file is missing,
    delete every cached icon whose source key is a .lnk so the next
    extraction pass picks up the resolver behaviour, then drop the
    sentinel so subsequent boots are no-ops.  Non-.lnk launchers
    (shell:, .exe) are left alone — they didn't have the arrow problem.

    The sentinel lives in Documents/Data/ — the canonical runtime
    cache home — *not* in icons/, which is reserved for actual icon
    assets.  The cached launcher icons themselves still live in
    icons/ alongside everything else; only the version marker moves
    out so the asset folder stays clean.
    """
    data_d = _data_dir()
    sentinel = data_d / _LAUNCHER_PIPELINE_SENTINEL

    # One-time migration: if the sentinel exists at the legacy
    # location (icons/), the user's cached icons are already on the
    # current pipeline version — port the marker to the new home
    # rather than triggering a needless re-extraction cycle.
    legacy_sentinel = d / _LAUNCHER_PIPELINE_SENTINEL
    if legacy_sentinel.exists():
        try:
            data_d.mkdir(parents=True, exist_ok=True)
            if not sentinel.exists():
                sentinel.touch()
            legacy_sentinel.unlink()
            _log.info("[app_icons] migrated sentinel: icons/ → Documents/Data/")
        except OSError as e:
            _log.warning(f"[app_icons] sentinel migration failed: {e}")

    if sentinel.exists():
        return
    for key, filename in _LAUNCHER_ICON_MAP.items():
        if key.startswith("shell:") or not key.lower().endswith(".lnk"):
            continue
        stale = d / filename
        if stale.exists():
            try:
                stale.unlink()
                _log.info(f"[app_icons] self-heal: invalidated stale {filename}")
            except OSError as e:
                _log.warning(f"[app_icons] self-heal failed to drop {filename}: {e}")
    try:
        data_d.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
    except OSError as e:
        _log.warning(f"[app_icons] self-heal failed to write sentinel: {e}")


def ensure_app_icons() -> None:
    """Check every registered extension and launcher; extract or refresh as needed.

    Call after QApplication exists (QFileIconProvider needs it).  Cost is
    negligible on subsequent boots — if nothing is stale, just a handful
    of stat() calls.  Freshly-installed machine's first boot does the
    extraction work, which takes milliseconds per icon.
    """
    d = icons_dir()
    # One-shot self-heal: drop .lnk-sourced cache entries that were
    # extracted under a previous pipeline version (e.g. with the shell
    # overlay arrow baked in).  No-op once the sentinel exists.
    _self_heal_lnk_cache(d)
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
