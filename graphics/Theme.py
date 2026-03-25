#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Theme.py
-Live view over settings.toml. Reads from settings, exposes as Python attributes.
-Helper methods for QPixmap caching, QColor construction, and derived values.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtGui import QColor, QPixmap, QPainter, QBrush
from pathlib import Path
import os as _os
import utils.settings as settings
from utils.logger import setup_logger as _setup_logger

_log = _setup_logger("theme")


_MISSING_ICON = "__missing__"   # Sentinel — Theme.icon() draws a circle for this


class _ThemeMeta(type):
    """
    Metaclass for Theme. The kitchen that never sends the waiter back empty handed.

    When any attribute lookup fails on Theme, instead of AttributeError,
    returns the _MISSING_ICON sentinel string. That sentinel travels through
    whatever the callsite does with it and lands in Theme.icon() which
    recognises it and draws a circle — visible, honest, requires nothing
    from the callsite.

    The entire fallback chain lives here. Callsites write Theme.iconAnything
    freely. If the TOML hasn't set it yet, a circle appears. No crashes,
    no empty plates, no changes needed anywhere else ever.
    """
    def __getattr__(cls, name: str) -> str:
        return _MISSING_ICON


class Theme(metaclass=_ThemeMeta):
    """
    Single source of truth for all visual values across the entire app.

    Values flow in one direction:
        settings.toml → utils/settings.py → Theme → every widget and node

    Theme never writes to settings.toml directly — that's settings.py's job.
    When settings.toml changes (written by The Settlers or anyone else),
    settings.py calls Theme.reload() which pulls new values in and clears
    the icon cache so repaints pick up the changes automatically.

    Hardcoded values here are only those that are structural constants —
    things that are genuinely not user-configurable and have no reason to
    live in a config file (animation physics, minimum sizes, padding ratios).
    Everything the user might want to change lives in settings.toml.
    """

    # =========================================================================
    # GLOBAL — sourced from [theme.colors] in settings.toml
    # =========================================================================
    # These are populated by reload() at startup and on every file change.
    # Accessing them before reload() runs returns the hardcoded fallback below.

    windowBg        = "#282828"
    primaryBorder   = "#6b5a47"
    textPrimary     = "#d2d1cf"
    backDrop        = "#2a2a3a"

    # Derived / structural — not in settings.toml, not user-configurable
    windowBorderWidth   = 1
    toolbarBorder       = primaryBorder
    toolbarBg           = windowBg
    layoutMargins       = (10, 5, 10, 5)
    handleHeightTop     = 35
    handleHeightBottom  = 100
    windowRollTiming    = 600

    # =========================================================================
    # SIDEBAR
    # =========================================================================

    sidebarPadding      = 6
    sidebarButtonGap    = 6
    sidebarCategoryGap  = 16

    @classmethod
    def sidebarWidth(cls) -> int:
        return cls.iconButtonSize + cls.sidebarPadding * 2

    # =========================================================================
    # BUTTONS
    # =========================================================================

    buttonPrimaryColor       = windowBg
    buttonInactiveColor      = "#1f1f1f"
    buttonFontFamily         = "Reey"
    buttonFontSize           = 22
    buttonFontBold           = False
    buttonTextVerticalOffset = -2
    buttonBorderWidth        = 1
    buttonBorderEnabled      = False
    buttonMinWidth           = 160
    buttonMinHeight          = 75

    buttonBg             = buttonPrimaryColor
    buttonBgHover        = buttonPrimaryColor
    buttonBgInactive     = buttonInactiveColor
    buttonBorder         = primaryBorder
    buttonBorderHover    = primaryBorder
    buttonBorderInactive = buttonInactiveColor

    iconButtonSize  = handleHeightTop - 3
    iconPadding     = 12
    iconSize        = 32

    # =========================================================================
    # COMBOBOX
    # =========================================================================

    comboboxBg            = windowBg
    comboboxBgOpen        = backDrop
    comboboxText          = textPrimary
    comboboxBorder        = primaryBorder
    comboboxBorderRadius  = 9
    comboboxPadding       = "3px 12px"
    comboboxFontFamily    = "Segoe UI"
    comboboxFontSize      = 9
    comboboxFontWeight    = "normal"
    comboboxDropdownWidth = 30
    comboboxMinWidth      = 350

    # =========================================================================
    # NODES
    # =========================================================================

    nodeBg                  = "#2a2a2a"
    nodeBorder              = primaryBorder
    nodeBorderSelected      = textPrimary
    nodeBorderWidth         = 1.5
    nodeBorderSelectedScale = 1.8
    nodeRoundRadius         = 12.0
    nodeShadowBlur          = 28
    nodeShadowColor         = "#5a000000"
    nodeShadowOffsetX       = 0
    nodeShadowOffsetY       = 4
    nodeShadowMargin        = 40
    nodeMinWidth            = 120.0
    nodeMinHeight           = 50.0
    nodeResizeGrip          = 16
    nodePulseScale          = 1.018
    nodePulseMinMs          = 800
    nodePulseMaxMs          = 1400

    # =========================================================================
    # BEZIER NODE
    # =========================================================================

    bezierCurveColor    = "#a89a8a"
    bezierCurveColorSel = "#d2d1cf"
    bezierCurveWidth    = 2.5
    bezierHandleColor   = "#6b5a47"
    bezierHandleHover   = "#d2d1cf"
    bezierArmColor      = "#4a3d33"
    bezierArmWidth      = 1.0
    bezierHandleRadius  = 6.0

    # =========================================================================
    # HEALTH NODE
    # =========================================================================

    healthNodeBg         = "#1e2230"
    healthNodeWidth      = 260.0
    healthNodeHeight     = 230.0
    healthColorLabel     = "#a89a8a"
    healthColorCalm      = "#8cbea0"
    healthColorWarn      = "#d4a96a"
    healthColorHigh      = "#c97b7b"
    healthWarnThreshold  = 50
    healthHighThreshold  = 150
    healthPollIntervalMs = 2000
    healthFontFamily     = "Segoe UI"
    healthFontSizeLabel  = 8
    healthFontSizeValue  = 9
    healthFontSizeHeader = 10
    healthFontSizeFooter = 7

    # =========================================================================
    # ICON CACHE
    # =========================================================================

    _icon_cache: dict = {}

    # Vault subfolder for icons — matches the vault's one-level structure
    _VAULT_SUBFOLDER = "icons"

    @classmethod
    def _resolve_icon_path(cls, filename: str) -> Path | None:
        """
        Resolve a filename to an absolute path using the two-level lookup:

            1. ./icons/  — local project folder, ships with the repo.
                           Project-specific overrides always win.
            2. $SingleSharedBraincell_AssetVault/icons/  — personal vault.
                           Never committed. Anyone outside the organisation
                           gets circles instead, which is correct behaviour.

        Returns the first Path that exists, or None if neither has the file.
        """
        from utils.logger import TRACE

        # 1. Local project icons/ — always checked first
        local = Path(__file__).parent.parent / "icons" / filename
        _log.log(TRACE, f"[icon resolve] '{filename}' → checking local: {local}")
        if local.exists():
            _log.debug(f"[icon resolve] '{filename}' → found locally: {local}")
            return local
        _log.log(TRACE, f"[icon resolve] '{filename}' → not in local icons/")

        # 2. Personal asset vault
        vault_root = _os.environ.get("SingleSharedBraincell_AssetVault")
        if not vault_root:
            _log.log(TRACE, f"[icon resolve] '{filename}' → SingleSharedBraincell_AssetVault not set")
        else:
            vault = Path(vault_root) / cls._VAULT_SUBFOLDER / filename
            _log.log(TRACE, f"[icon resolve] '{filename}' → checking vault: {vault}")
            if vault.exists():
                _log.debug(f"[icon resolve] '{filename}' → found in vault: {vault}")
                return vault
            else:
                _log.log(TRACE, f"[icon resolve] '{filename}' → not in vault (vault root: {vault_root})")

        _log.log(TRACE, f"[icon resolve] '{filename}' → not found anywhere — circle fallback")
        return None

    @classmethod
    def icon(cls, filename: str | None, fallback_color: str = "#6b5a47") -> QPixmap:
        """
        Return the cached QPixmap for filename, loading on first request.

        Resolution order:
            1. ./icons/filename                                — local override
            2. $SingleSharedBraincell_AssetVault/icons/filename — personal vault
            3. _make_circle()                                  — honest fallback

        If filename is None, empty, or the missing-icon sentinel — skips
        resolution entirely and returns a circle immediately.

        The cache key is the filename string. Once loaded from either location
        the pixmap is cached — zero per-frame resolution cost.
        """
        from utils.logger import TRACE

        # None, empty string, or the missing-icon sentinel → circle immediately
        if not filename or filename == _MISSING_ICON:
            _log.log(TRACE, f"[icon] sentinel/None → circle (fallback_color={fallback_color})")
            return cls._make_circle(fallback_color)

        if filename in cls._icon_cache:
            _log.log(TRACE, f"[icon] '{filename}' → cache hit")
            return cls._icon_cache[filename]

        _log.log(TRACE, f"[icon] '{filename}' → cache miss, resolving...")
        pix = None
        resolved = cls._resolve_icon_path(filename)
        if resolved:
            candidate = QPixmap(str(resolved))
            if not candidate.isNull():
                pix = candidate
                _log.debug(f"[icon] '{filename}' → loaded from {resolved}")
            else:
                _log.warning(f"[icon] '{filename}' → file exists at {resolved} but QPixmap is null")
        
        if pix is None:
            _log.log(TRACE, f"[icon] '{filename}' → drawing circle fallback")
            pix = cls._make_circle(fallback_color)

        cls._icon_cache[filename] = pix
        return pix

    @classmethod
    def _make_circle(cls, color: str) -> QPixmap:
        """Generate a plain filled circle pixmap. Used as the universal fallback."""
        size = 32
        pix  = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(color)))
        p.setPen(QColor(color))
        p.drawEllipse(2, 2, size - 4, size - 4)
        p.end()
        return pix

    @classmethod
    def invalidate_icon(cls, filename: str) -> None:
        """
        Remove a filename from the icon cache.
        Called by Theme.reload() when settings.toml reports a new icon path.
        Next call to Theme.icon(filename) will reload from disk.
        """
        cls._icon_cache.pop(filename, None)

    @classmethod
    def invalidate_all_icons(cls) -> None:
        """Clear the entire icon cache. Called on full theme reload."""
        cls._icon_cache.clear()

    # =========================================================================
    # RELOAD — called by settings watcher when settings.toml changes
    # =========================================================================

    @classmethod
    def reload(cls) -> None:
        """
        Pull current values from settings.toml into Theme attributes.

        Called automatically when the file watcher detects a change.
        Also called once at startup from main.py after settings are loaded.

        Order of operations:
            1. Read colors from [theme.colors] — update class attributes
            2. Read icons from [theme.icons] — update filename attributes
            3. Clear icon cache for any filename that changed
            4. Dependent attributes (combobox colors etc.) are recalculated
               from the new base values
        """
        # ── Colors ────────────────────────────────────────────────────────────
        colors = settings.get_section("theme").get("colors", {})

        if "window_bg" in colors:
            cls.windowBg        = colors["window_bg"]
            cls.toolbarBg       = cls.windowBg
            cls.buttonPrimaryColor = cls.windowBg
            cls.buttonBg        = cls.windowBg
            cls.buttonBgHover   = cls.windowBg
            cls.comboboxBg      = cls.windowBg

        if "primary_border" in colors:
            cls.primaryBorder       = colors["primary_border"]
            cls.toolbarBorder       = cls.primaryBorder
            cls.buttonBorder        = cls.primaryBorder
            cls.buttonBorderHover   = cls.primaryBorder
            cls.nodeBorder          = cls.primaryBorder
            cls.comboboxBorder      = cls.primaryBorder
            cls.bezierHandleColor   = cls.primaryBorder

        if "text_primary" in colors:
            cls.textPrimary         = colors["text_primary"]
            cls.comboboxText        = cls.textPrimary
            cls.nodeBorderSelected  = cls.textPrimary

        if "backdrop" in colors:
            cls.backDrop        = colors["backdrop"]
            cls.comboboxBgOpen  = cls.backDrop

        # ── Icons ─────────────────────────────────────────────────────────────
        # Attributes are created dynamically via setattr — they don't exist
        # on Theme until the TOML puts them there. Callsites use
        # getattr(Theme, 'iconWarm', None) so Theme.icon() receives None
        # and generates the circle fallback if the TOML hasn't loaded yet.
        #
        # If a key is present in icon_map but absent from the TOML:
        #   - invalidate any cached pixmap for the old filename
        #   - remove the attribute from Theme entirely
        # This ensures a missing TOML entry produces a circle on next paint,
        # even on a warm cache from a previous load.
        icon_map = {
            "curtains": "iconPathCurtains",
            "delete":   "iconDelete",
            "confirm":  "iconConfirm",
            "health":   "iconHealth",
            "warm":     "iconWarm",
            "about":    "iconAbout",
            "bezier":   "iconBezier",
            "image":    "iconImage",
        }
        icons = settings.get_section("theme").get("icons", {})
        for toml_key, attr_name in icon_map.items():
            new_filename = icons.get(toml_key)
            old_filename = getattr(cls, attr_name, None)

            if new_filename:
                # Key present — update if changed
                if old_filename != new_filename:
                    cls.invalidate_icon(old_filename or "")
                    setattr(cls, attr_name, new_filename)
            else:
                # Key missing or empty — invalidate cache and remove attribute
                # so next paint receives None and draws the circle fallback
                if old_filename:
                    cls.invalidate_icon(old_filename)
                try:
                    delattr(cls, attr_name)
                except AttributeError:
                    pass    # Already absent — nothing to do

    # =========================================================================
    # UTILITIES
    # =========================================================================

    @staticmethod
    def color(hex_str: str) -> QColor:
        """Construct a QColor from a Theme hex string on demand."""
        return QColor(hex_str)

    @staticmethod
    def to_hex(color) -> str:
        """Dev utility — convert QColor to HexArgb string."""
        return color.name(QColor.HexArgb)
