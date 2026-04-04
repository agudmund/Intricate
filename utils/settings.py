#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/settings.py TOML-backed settings loader
-Single source of truth on disk. File watcher notifies Theme on change for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# ─────────────────────────────────────────────────────────────────────────────
# APP IDENTITY  ← change these when forking to a new app
# ─────────────────────────────────────────────────────────────────────────────

appName = "Intricate"
orgName = "Single Shared Braincell"


import tomllib
from pathlib import Path
from typing import Any
from PySide6.QtCore import QFileSystemWatcher, QObject, Signal


# ─────────────────────────────────────────────────────────────────────────────
# PATH
# ─────────────────────────────────────────────────────────────────────────────

# SingleSharedBraincell_SettingsFile env var points all apps in the family
# at the same shared settings.toml — Intricate, The Settlers, any future app.
# Organisation-scoped so the contract is shared across all projects.
# Falls back to settings.toml next to main.py for development convenience.
#   Windows:  set SingleSharedBraincell_SettingsFile=C:\Users\you\Shared\settings.toml
import os as _os
import sys as _sys

_ENV_VAR = "SingleSharedBraincell_SettingsFile"

# When running as a PyInstaller bundle, __file__ points into the temp extraction
# dir (sys._MEIPASS), not the folder the exe lives in.  settings.toml must sit
# next to the exe — use sys.executable.parent so the watcher finds the real
# shared file regardless of whether we're frozen or running from source.
_default_settings = (
    Path(_sys.executable).resolve().parent / "settings.toml"
    if getattr(_sys, "frozen", False)
    else Path(__file__).resolve().parent.parent / "settings.toml"
)
_SETTINGS_PATH = Path(_os.environ.get(_ENV_VAR, str(_default_settings)))


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
# Written to disk on first run if settings.toml doesn't exist.
# This is the complete contract — every key Intricate reads or The Settlers writes.

_DEFAULTS: dict = {
    "window": {
        "width":  900,
        "height": 700,
        "x":      100,
        "y":      100,
    },
    "canvas": {
        "fog_alpha": 180,
    },
    "session": {
        "last_loaded": "",
    },
    "ui": {
        "sidebar_visible": True,
    },
    "apps": {
        # External app paths — resolved at launch time, never hardcoded.
        # Set to an exe path or leave empty to disable.
        # e.g. "warm_editor": "C:\\Apps\\NotepadDuplex.exe"
        "warm_editor": "",
    },
    "node": {
        "font_vertical_offset":       -8,
        "text_padding_left":          15,
        "text_padding_top":           4,
        "border_color":               "#6b5a47",
        "border_hover_color":         "#8a7560",
        "border_selected_color":      "#a38f7b",
        "font_color":                 "#d2d1cf",
        "claude": {
            "bg_color":          "#1e2a22",
            "bg_color_front":    "#28201e",
            "bg_alpha":          179,
            "body_font_family":  "Lato",
            "body_font_size":    10,
            "default_width":     200,
            "default_height":    300,
        },
        "about": {
            "editor_vertical_offset": 0,
            "font_size": 10,
            "font_vertical_offset": -8,
            "bg_color": "#2a2a2a",
            "bg_color_front": "#322a3a",
            "bg_alpha": 180,
            "depth_icon_off": "depth_off.png",
            "depth_icon_on": "depth_on.png",
            "min_height": 42,
            "line_spacing": 0,
            "text_padding_left": 15,
            "text_padding_top": 4,
            "selection_line_height": 0,
            "selection_font_color": "#ffffff",
        },
    },
    "theme": {
        "icons": {
            # No defaults — missing icons produce circles via Theme._make_circle().
            # A circle is the honest "no icon configured" state.
            # The Settlers writes real filenames here when the user sets them.
        },
        "colors": {
            # Colors always need a valid value — defaults ensure Intricate
            # renders correctly even before The Settlers has run.
            "window_bg":      "#282828",
            "primary_border": "#6b5a47",
            "text_primary":   "#d2d1cf",
            "backdrop":       "#2a2a3a",
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# WATCHER — emits changed() when settings.toml is written by any process
# ─────────────────────────────────────────────────────────────────────────────

class _SettingsWatcher(QObject):
    """
    Watches settings.toml for changes from any source — Intricate itself,
    The Settlers, a text editor, anything. When the file changes, emits
    changed() so Theme can reload and the scene can repaint.

    QFileSystemWatcher fires on any write to the watched path regardless
    of which process caused it. That's the entire point — the handshake
    between Intricate and The Settlers requires no direct connection.

    This handler is armored: nothing that happens inside — bad TOML,
    permission errors, mid-write partial files — can kill the watcher.
    A dead watcher means the entire live-reload pipeline goes silent
    with no visible symptom. That must never happen.
    """
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._watcher = QFileSystemWatcher()
        self._ensure_watched()
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _ensure_watched(self) -> None:
        """
        (Re-)add the settings path to the watcher.

        Wrapped in its own try/except because even Path.exists() can throw
        on permission errors or broken symlinks, and addPath silently fails
        on non-existent files. Neither case should take us down.
        """
        try:
            path_str = str(_SETTINGS_PATH)
            # addPath is idempotent — returns False if already watched or missing,
            # never throws. But we guard the exists() check that precedes it.
            if _SETTINGS_PATH.exists():
                self._watcher.addPath(path_str)
            else:
                # File doesn't exist yet (mid delete+recreate cycle).
                # Watch the parent directory so we catch the recreate.
                parent = str(_SETTINGS_PATH.parent)
                if _SETTINGS_PATH.parent.exists():
                    self._watcher.addPath(parent)
        except Exception:
            # Filesystem is acting up — log and survive.
            # The next fileChanged or directoryChanged event will retry.
            try:
                from utils.logger import setup_logger
                setup_logger("settings").warning(
                    "[watcher] could not re-add settings path — will retry on next event",
                    exc_info=True
                )
            except Exception:
                pass  # Even logging failed — stay alive regardless

    def _on_file_changed(self, path: str) -> None:
        """
        Handle a file-change notification.

        Armored with a blanket try/except so nothing — tomllib parse errors,
        type conversion failures, permission issues, mid-write partial files,
        Theme.reload() bugs — can kill this handler. A dead handler means
        the watcher stays connected but stops processing events. The entire
        live-reload pipeline dies silently. That is the one thing we prevent.

        Order of operations is deliberate:
            1. Re-add path FIRST — if the reload crashes, at least the watcher
               is still alive for the next save.
            2. Reload the store.
            3. Emit changed() so Theme picks up new values.
        """
        # Step 1: Re-add path unconditionally. This is the most critical step.
        # Some editors (Notepad++, vim) write by delete+recreate which removes
        # the path from QFileSystemWatcher. If we don't re-add, all future
        # changes are missed forever.
        self._ensure_watched()

        # Step 2+3: Reload and notify. Wrapped so a bad file never kills us.
        try:
            _reload()
            self.changed.emit()
        except Exception:
            # Bad TOML, mid-write partial file, disk error — whatever it is,
            # the old _store is still intact (reload is atomic, see below).
            # Log the problem so the user can fix their TOML and save again.
            try:
                from utils.logger import setup_logger
                setup_logger("settings").warning(
                    "[watcher] settings.toml reload failed — keeping previous values. "
                    "Save the file again once it's valid.",
                    exc_info=True
                )
            except Exception:
                pass  # Even logging failed — the watcher lives on


# Module-level watcher instance — created once, lives for the app lifetime.
# Accessed via settings.watcher.changed.connect(your_slot).
watcher: _SettingsWatcher | None = None


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY STORE
# ─────────────────────────────────────────────────────────────────────────────

_store: dict = {}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Merge override into base recursively.
    Keys present in base but missing from override keep their default values.
    This ensures new keys added to _DEFAULTS are always available even if
    an older settings.toml on disk doesn't have them yet.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _reload() -> None:
    """
    Read settings.toml from disk and merge with defaults.

    Atomic by design: the new store is built in a local variable first.
    Only after the entire parse+merge succeeds does it replace _store.
    If anything fails — bad TOML, partial file, permission error — the
    old _store remains untouched. The caller (watcher) catches the
    exception and logs it; the next file-save will trigger a fresh attempt.

    This is the DMX patch bay — it may never leave the system in a
    half-updated state.
    """
    global _store
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "rb") as f:
            from_disk = tomllib.load(f)
        # Build the merged store in a local — only assign to _store on success.
        # This ensures a tomllib error or a _deep_merge edge case never
        # corrupts the live store.
        merged = _deep_merge(_DEFAULTS, from_disk)
        _store = merged
    else:
        _store = dict(_DEFAULTS)
        _save()     # Write defaults to disk on first run


def _save() -> None:
    """
    Write current store to disk as TOML.

    tomllib is read-only (stdlib). We write manually — TOML is simple
    enough that a lightweight writer keeps us dependency-free.
    For the nested [theme.icons] and [theme.colors] structure we need
    to handle subtables explicitly.
    """
    lines = [f"# {appName} — settings.toml",
             f"# Shared contract between {appName} and The Settlers.",
             f"# {appName} reads and watches this file. The Settlers writes to it.",
             "# Neither project imports the other. This file is the entire handshake.",
             ""]

    def _write_section(d: dict, prefix: str = "") -> list[str]:
        out = []
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        tables  = {k: v for k, v in d.items() if isinstance(v, dict)}

        for k, v in scalars.items():
            if isinstance(v, str):
                out.append(f'{k} = "{v.replace(chr(92), chr(92)*2)}"')
            elif isinstance(v, bool):
                out.append(f'{k} = {"true" if v else "false"}')
            else:
                out.append(f"{k} = {v}")

        for k, v in tables.items():
            section = f"{prefix}.{k}" if prefix else k
            out.append(f"\n[{section}]")
            out.extend(_write_section(v, section))

        return out

    for section, values in _store.items():
        if isinstance(values, dict):
            # Check if it has subtables
            has_subtables = any(isinstance(v, dict) for v in values.values())
            def _fmt(k, v) -> str:
                if isinstance(v, str):
                    return f'{k} = "{v.replace(chr(92), chr(92)*2)}"'
                elif isinstance(v, bool):
                    return f'{k} = {"true" if v else "false"}'
                return f"{k} = {v}"

            if not has_subtables:
                lines.append(f"\n[{section}]")
                for k, v in values.items():
                    lines.append(_fmt(k, v))
            else:
                scalars = {k: v for k, v in values.items() if not isinstance(v, dict)}
                tables  = {k: v for k, v in values.items() if isinstance(v, dict)}
                if scalars:
                    lines.append(f"\n[{section}]")
                    for k, v in scalars.items():
                        lines.append(_fmt(k, v))
                for sub_k, sub_v in tables.items():
                    lines.append(f"\n[{section}.{sub_k}]")
                    for k, v in sub_v.items():
                        lines.append(_fmt(k, v))

    _SETTINGS_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def get(section: str, key: str, default: Any = None) -> Any:
    """Read a scalar value from a top-level section."""
    return _store.get(section, {}).get(key, default)


def get_section(section: str) -> dict:
    """Read an entire section. Returns empty dict if missing."""
    return dict(_store.get(section, {}))


def get_nested(section: str, subsection: str, key: str, default: Any = None) -> Any:
    """Read a value from a nested section e.g. get_nested('theme', 'icons', 'warm')."""
    return _store.get(section, {}).get(subsection, {}).get(key, default)


def set_value(section: str, key: str, value: Any) -> None:
    """Write a scalar value and persist immediately."""
    if section not in _store:
        _store[section] = {}
    _store[section][key] = value
    _save()


def set_nested(section: str, subsection: str, key: str, value: Any) -> None:
    """Write a nested value and persist immediately."""
    if section not in _store:
        _store[section] = {}
    if subsection not in _store[section]:
        _store[section][subsection] = {}
    _store[section][subsection][key] = value
    _save()


# ── Convenience accessors ──────────────────────────────────────────────────

def get_fog_alpha() -> int:
    return int(get("canvas", "fog_alpha", 180))

def set_fog_alpha(value: int) -> None:
    set_value("canvas", "fog_alpha", max(0, min(255, value)))

def get_icon(name: str) -> str:
    """Get an icon filename from [theme.icons]. e.g. get_icon('warm')"""
    return get_nested("theme", "icons", name, "")

def get_color(name: str) -> str:
    """Get a color hex string from [theme.colors]. e.g. get_color('window_bg')"""
    return get_nested("theme", "colors", name, "")


# ── Masked values (lightweight obfuscation for sensitive config) ─────────────

def _mask(text: str) -> str:
    """Base64-encode a string for storage obfuscation."""
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _unmask(masked: str) -> str:
    """Decode a base64-masked string. Returns empty string on failure."""
    import base64
    try:
        return base64.b64decode(masked.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def get_masked(section: str, key: str, default: str = "") -> str:
    """Retrieve and unmask a base64-obfuscated value."""
    raw = get(section, key, "")
    return _unmask(raw) if raw else default


def set_masked(section: str, key: str, value: str) -> None:
    """Mask a value with base64 and persist it."""
    set_value(section, key, _mask(value))


# ─────────────────────────────────────────────────────────────────────────────
# INITIALISE
# ─────────────────────────────────────────────────────────────────────────────

def init_watcher() -> _SettingsWatcher:
    """
    Create and return the file watcher. Called once from main.py after
    QApplication exists (QFileSystemWatcher requires an active event loop).
    Store the returned watcher — connect watcher.changed to your reload slot.
    """
    global watcher
    watcher = _SettingsWatcher()
    return watcher


# Load on import — synchronous, happens once at startup before any UI exists.
_reload()
