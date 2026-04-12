#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/registry.py node registry loader
-Reads node_registry.toml and provides category-grouped lookups for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import logging
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PATH
# ─────────────────────────────────────────────────────────────────────────────

def _registry_path() -> Path:
    """Resolve node_registry.toml — next to main.py or frozen exe."""
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        base = Path(_sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "node_registry.toml"


# ─────────────────────────────────────────────────────────────────────────────
# STORE
# ─────────────────────────────────────────────────────────────────────────────

_nodes: dict[str, dict] = {}
_actions: dict[str, dict] = {}


def _load() -> None:
    """Read node_registry.toml into the module-level stores."""
    global _nodes, _actions
    path = _registry_path()
    if not path.exists():
        _log.warning(f"[registry] {path} not found — menus will use fallback names")
        return
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        _nodes = dict(data.get("nodes", {}))
        _actions = dict(data.get("actions", {}))
        _log.info(f"[registry] loaded {len(_nodes)} nodes, {len(_actions)} actions")
    except Exception:
        _log.warning("[registry] failed to parse node_registry.toml", exc_info=True)


def reload() -> None:
    """Re-read the registry from disk. Called by the watcher on file change."""
    _load()


def get_node(type_key: str) -> dict:
    """Return the registry entry for a node type, or empty dict."""
    return dict(_nodes.get(type_key, {}))


def get_nodes_by_category(category: str) -> list[tuple[str, dict]]:
    """Return [(type_key, entry_dict), ...] for all nodes in a category.

    Preserves TOML file order (insertion order) so the menu reads
    in the same sequence as the registry file.
    """
    return [
        (key, dict(entry))
        for key, entry in _nodes.items()
        if entry.get("category") == category and entry.get("spawnable", True)
    ]


def get_actions_by_category(category: str) -> list[tuple[str, dict]]:
    """Return [(action_key, entry_dict), ...] for non-node actions in a category."""
    return [
        (key, dict(entry))
        for key, entry in _actions.items()
        if entry.get("category") == category
    ]


def get_all_nodes() -> dict[str, dict]:
    """Return the full node registry as a dict of dicts."""
    return dict(_nodes)


# ─────────────────────────────────────────────────────────────────────────────
# WATCHER
# ─────────────────────────────────────────────────────────────────────────────

class _RegistryWatcher(QObject):
    """Watches node_registry.toml for changes and reloads the registry."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._watcher = QFileSystemWatcher()
        self._ensure_watched()
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _ensure_watched(self) -> None:
        path = str(_registry_path())
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    def _on_file_changed(self, path: str) -> None:
        self._ensure_watched()
        try:
            reload()
            self.changed.emit()
        except Exception:
            _log.warning("[registry] reload failed after file change", exc_info=True)


watcher: _RegistryWatcher | None = None


def init_watcher() -> _RegistryWatcher:
    """Create the file watcher. Call after QApplication exists."""
    global watcher
    _load()
    watcher = _RegistryWatcher()
    return watcher
