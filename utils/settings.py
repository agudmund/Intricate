#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Cozy times nodal playground - utils/settings.py
-Unified, cozy settings using QSettings with a local .ini fallback for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional
from PySide6.QtCore import QSettings
from utils.logger import setup_logger

class Settings:
    """
    Singleton wrapper for QSettings.
    Uses 'IniFormat' to ensure settings are stored in a human-readable file 
    rather than the messy Windows Registry.
    """

    _instance: Optional[QSettings] = None
    _logger = None

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            cls._logger = setup_logger("settings")
        return cls._logger

    @classmethod
    def _get_instance(cls) -> QSettings:
        """Initialize QSettings to point to a local .ini file."""
        if cls._instance is None:
            # Determine path: Next to EXE if bundled, or in project root if script
            if hasattr(sys, '_MEIPASS'):
                base_path = Path(sys.executable).parent
            else:
                base_path = Path(__file__).resolve().parent.parent

            settings_path = base_path / "nodal_config.ini"
            
            # Use IniFormat for a portable, human-readable file
            cls._instance = QSettings(str(settings_path), QSettings.IniFormat)
            cls._get_logger().debug(f"Settings initialized at: {settings_path}")
            
        return cls._instance

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Standard getter with a default fallback."""
        return cls._get_instance().value(key, default)

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Defensive getter for booleans to prevent string-conversion bugs."""
        val = cls.get(key, default)
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "on")
        return bool(val)

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Defensive getter for integers."""
        try:
            return int(cls.get(key, default))
        except (ValueError, TypeError):
            return default

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """Sets a value and forces a sync to disk."""
        cls._get_instance().setValue(key, value)
        cls._get_instance().sync()

    # ── High-Level Convenience Methods ──────────────────────────────────────

    @classmethod
    def is_high_dpi_enabled(cls) -> bool:
        return cls.get_bool("interface/high_dpi", True)

    @classmethod
    def set_high_dpi(cls, enabled: bool):
        cls.set("interface/high_dpi", enabled)

    @classmethod
    def get_default_node_label(cls) -> str:
        return str(cls.get("nodes/default_label", "Nodal 🌱"))

    @classmethod
    def get_window_geometry(cls):
        """Returns the saved byte array for window size/pos."""
        return cls.get("window/geometry")

    @classmethod
    def set_window_geometry(cls, geometry):
        cls.set("window/geometry", geometry)

    @classmethod
    def get_recovery_interval(cls) -> int:
        """Recovery write quiet period in seconds (default 2)."""
        return cls.get_int("scene/recovery_interval_secs", 2)

    @classmethod
    def set_recovery_interval(cls, seconds: int):
        cls.set("scene/recovery_interval_secs", seconds)

    @classmethod
    def is_debug_overlay_enabled(cls) -> bool:
        """Show bounding rect, shape, and port crosshairs on nodes."""
        return cls.get_bool("debug/node_overlay", False)

    @classmethod
    def set_debug_overlay(cls, enabled: bool):
        cls.set("debug/node_overlay", enabled)