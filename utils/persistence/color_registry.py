#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/persistence/color_registry.py live palette registry
-and they learnt to whisper to each other across color_registry.toml for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

from shared_braincell.logger import setup_logger

_log = setup_logger("color_registry")


# The fallback palette used when color_registry.toml is missing or empty.
# Curated from the Paradisic Fields project palette.  Matches the historical
# _DEFAULT_COLORS in utils/pickers/ColorPicker.py — preserved here so first-run
# and recovery-from-missing-file still yield the same familiar four.
_SEED_COLORS: tuple[str, ...] = (
    "#2a2f3a",  # dusk slate
    "#b05f5f",  # old brick
    "#4a3a5a",  # plum shadow
    "#1e1e1e",  # charcoal
)


# ─────────────────────────────────────────────────────────────────────────────
# PATH
# ─────────────────────────────────────────────────────────────────────────────

def registry_path() -> Path:
    """Resolve color_registry.toml — next to main.py or frozen exe.

    This file lives at utils/persistence/color_registry.py so repo root
    is three parents up (matches registry.py's walk).
    """
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / "color_registry.toml"


# ─────────────────────────────────────────────────────────────────────────────
# STORE
# ─────────────────────────────────────────────────────────────────────────────

_colors: list[str] = list(_SEED_COLORS)


def _normalize(hex_color: str) -> str:
    """Canonical form for palette comparison — lowercase, leading #."""
    s = (hex_color or "").strip().lower()
    if s and not s.startswith("#"):
        s = "#" + s
    return s


def _read_file() -> list[str] | None:
    """Parse color_registry.toml. Returns the palette list or None on error."""
    path = registry_path()
    if not path.exists():
        return None
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        _log.warning("[color_registry] failed to parse file", exc_info=True)
        return None
    palette = data.get("palette", {})
    raw = palette.get("colors", [])
    if not isinstance(raw, list):
        return None
    # Normalize and dedupe while preserving order
    seen = set()
    out: list[str] = []
    for c in raw:
        if not isinstance(c, str):
            continue
        n = _normalize(c)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _write_file(colors: list[str]) -> bool:
    """Write the palette list to color_registry.toml. Preserves the header
    comment block if the file already exists — we re-emit the intro text so
    the file remains self-documenting on first creation.

    Returns True on success.  Failure is logged, never raised — the live
    palette continues working from the in-memory copy.
    """
    path = registry_path()
    try:
        import tomli_w
    except ModuleNotFoundError:
        _log.warning("[color_registry] tomli_w not installed — cannot write registry")
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    header = (
        "# Color Registry — the live palette for Intricate's node tint cycle.\n"
        "#\n"
        "# Intricate writes here when a custom color enters rotation (via the tint\n"
        "# toggle on a node, or when a session loads a node whose data.node_tint\n"
        "# is not yet in the palette).  The Settlers reads this file and its Color\n"
        "# Picker category lets you curate the list — × a color to remove it from\n"
        "# future rotations.  Both apps watch this file so edits from either side\n"
        "# land live.\n"
        "#\n"
        "# Role split, for reference:\n"
        "#   settings.toml         — The Settlers writes (control-board output)\n"
        "#   color_registry.toml   — shared stage-state; Intricate reports, The\n"
        "#                           Settlers curates, both watch for changes.\n"
        "#\n"
        "# Order matters — the tint toggle rotates in the order listed here.\n"
        "\n"
    )
    body = tomli_w.dumps({"palette": {"colors": colors}})
    try:
        # Atomic swap — write to sibling temp then rename, so a crash mid-write
        # doesn't leave a half-file the watchers pick up.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(header + body, encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        _log.warning("[color_registry] write failed", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def load() -> list[str]:
    """Read color_registry.toml into the in-memory palette.

    If the file is missing, seed with _SEED_COLORS and write it back so the
    file exists on subsequent runs.  Always returns the resulting list.
    """
    global _colors
    parsed = _read_file()
    if parsed is None:
        _colors = list(_SEED_COLORS)
        _write_file(_colors)
    else:
        _colors = parsed if parsed else list(_SEED_COLORS)
    return list(_colors)


def reload() -> list[str]:
    """Re-read from disk. Called by the watcher on file change."""
    return load()


def get_all() -> list[str]:
    """Return the current palette as a fresh list."""
    return list(_colors)


def register(hex_color: str) -> int:
    """Ensure *hex_color* is in the palette and persist. Returns its index.

    Idempotent — colors already present (case-insensitive) return their
    existing index without duplication.  Empty input returns -1 (no-op).
    """
    norm = _normalize(hex_color)
    if not norm:
        return -1
    for i, c in enumerate(_colors):
        if c == norm:
            return i
    _colors.append(norm)
    _write_file(_colors)
    return len(_colors) - 1


def remove(hex_color: str) -> bool:
    """Remove *hex_color* from the palette if present. Persists the change.

    Returns True if a color was removed.  Used by The Settlers' × action
    on color pills — and also safe for Intricate to call if a future flow
    needs to drop a color.
    """
    norm = _normalize(hex_color)
    if not norm:
        return False
    for i, c in enumerate(_colors):
        if c == norm:
            _colors.pop(i)
            _write_file(_colors)
            return True
    return False


def set_all(colors: Iterable[str]) -> list[str]:
    """Replace the palette wholesale with *colors* (normalized, deduped).
    Persists and returns the new list.  Primary Settlers-side write path
    once the Color Picker category is live.
    """
    seen = set()
    out: list[str] = []
    for c in colors:
        n = _normalize(c)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    _colors.clear()
    _colors.extend(out)
    _write_file(_colors)
    return list(_colors)


# ─────────────────────────────────────────────────────────────────────────────
# WATCHER
# ─────────────────────────────────────────────────────────────────────────────

class _ColorRegistryWatcher(QObject):
    """Watches color_registry.toml for changes and reloads the palette."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._watcher = QFileSystemWatcher()
        self._ensure_watched()
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _ensure_watched(self) -> None:
        path = str(registry_path())
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    def _on_file_changed(self, _path: str) -> None:
        # Some editors replace-on-save (atomic swap); re-add so we keep tracking.
        self._ensure_watched()
        try:
            reload()
            self.changed.emit()
        except Exception:
            _log.warning("[color_registry] reload failed after file change", exc_info=True)


watcher: _ColorRegistryWatcher | None = None


def init_watcher() -> _ColorRegistryWatcher:
    """Load once and create the file watcher. Call after QApplication exists."""
    global watcher
    load()
    watcher = _ColorRegistryWatcher()
    return watcher
