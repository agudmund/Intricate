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
import utils.settings as settings


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

    @classmethod
    def icon(cls, filename: str | None, fallback_color: str = "#6b5a47") -> QPixmap:
        """
        Return the cached QPixmap for filename, loading on first request.

        Resolves filename relative to the icons/ folder at the project root.
        If filename is None, empty, or the file is missing — generates a
        filled circle in fallback_color. This is the honest representation
        of 'no icon configured' and requires no fallback values elsewhere.

        Called by every button and node that needs an icon. The cache means
        thirty nodes sharing the same delete icon share one GPU texture.
        """
        # None, empty string, or the missing-icon sentinel → circle immediately
        if not filename or filename == _MISSING_ICON:
            return cls._make_circle(fallback_color)

        if filename in cls._icon_cache:
            return cls._icon_cache[filename]

        icon_path = Path(__file__).parent.parent / "icons" / filename
        pix = None

        if icon_path.exists():
            candidate = QPixmap(str(icon_path))
            if not candidate.isNull():
                pix = candidate

        if pix is None:
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
