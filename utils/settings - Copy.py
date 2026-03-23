#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/settings.py settings module
-TOML-backed settings. Read on startup, written on change for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import tomllib
from pathlib import Path
from typing import Any


_SETTINGS_PATH = Path(__file__).parent.parent / "settings.toml"
_store: dict = {}


def _load() -> None:
    global _store
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "rb") as f:
            _store = tomllib.load(f)
    else:
        _store = {}


def _save() -> None:
    """Write settings to disk. Minimal TOML writer — no extra dependencies."""
    lines = []
    for section, values in _store.items():
        lines.append(f"\n[{section}]")
        for key, value in values.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key} = {"true" if value else "false"}')
            else:
                lines.append(f"{key} = {value}")
    _SETTINGS_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def get(section: str, key: str, default: Any = None) -> Any:
    return _store.get(section, {}).get(key, default)


def set_value(section: str, key: str, value: Any) -> None:
    """Write a value and persist to disk immediately."""
    if section not in _store:
        _store[section] = {}
    _store[section][key] = value
    _save()


def get_fog_alpha() -> int:
    return int(get("canvas", "fog_alpha", 180))


def set_fog_alpha(value: int) -> None:
    set_value("canvas", "fog_alpha", max(0, min(255, value)))


_load()
