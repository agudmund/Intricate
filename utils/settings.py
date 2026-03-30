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
_ENV_VAR       = "SingleSharedBraincell_SettingsFile"
_SETTINGS_PATH = Path(
    _os.environ.get(
        _ENV_VAR,
        str(Path(__file__).resolve().parent.parent / "settings.toml")
    )
)


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
        "font_vertical_offset": -8,
        "text_padding_left":    15,
        "text_padding_top":     4,
        "claude": {
            "bg_color":       "#1e2a22",
            "bg_color_front": "#28201e",
            "bg_alpha":       179,
        },
        "about": {
            "editor_vertical_offset": 0,
            "font_size": 10,
            "font_color": "#e8f0ff",
            "bg_color": "#2a2a2a",
            "bg_color_front": "#322a3a",
            "bg_alpha": 180,
            "border_color": "#6b5a47",
            "border_hover_color": "#8a7560",
            "border_selected_color": "#8a7560",
            "depth_icon_off": "depth_off.png",
            "depth_icon_on": "depth_on.png",
            "min_height": 42,
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
    """
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._watcher = QFileSystemWatcher()
        if _SETTINGS_PATH.exists():
            self._watcher.addPath(str(_SETTINGS_PATH))
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _on_file_changed(self, path: str) -> None:
        """
        Re-add the path after change — some editors write by delete+recreate
        which removes the path from the watcher. Re-adding is idempotent.
        """
        if _SETTINGS_PATH.exists():
            self._watcher.addPath(str(_SETTINGS_PATH))
        _reload()
        self.changed.emit()


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
    """Read settings.toml from disk and merge with defaults."""
    global _store
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "rb") as f:
            from_disk = tomllib.load(f)
        _store = _deep_merge(_DEFAULTS, from_disk)
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
                out.append(f'{k} = "{v}"')
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
            if not has_subtables:
                lines.append(f"\n[{section}]")
                for k, v in values.items():
                    if isinstance(v, str):
                        lines.append(f'{k} = "{v}"')
                    elif isinstance(v, bool):
                        lines.append(f'{k} = {"true" if v else "false"}')
                    else:
                        lines.append(f"{k} = {v}")
            else:
                # Write subtables as [section.subsection]
                scalars = {k: v for k, v in values.items() if not isinstance(v, dict)}
                tables  = {k: v for k, v in values.items() if isinstance(v, dict)}
                if scalars:
                    lines.append(f"\n[{section}]")
                    for k, v in scalars.items():
                        if isinstance(v, str):
                            lines.append(f'{k} = "{v}"')
                        elif isinstance(v, bool):
                            lines.append(f'{k} = {"true" if v else "false"}')
                        else:
                            lines.append(f"{k} = {v}")
                for sub_k, sub_v in tables.items():
                    lines.append(f"\n[{section}.{sub_k}]")
                    for k, v in sub_v.items():
                        if isinstance(v, str):
                            lines.append(f'{k} = "{v}"')
                        elif isinstance(v, bool):
                            lines.append(f'{k} = {"true" if v else "false"}')
                        else:
                            lines.append(f"{k} = {v}")

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
