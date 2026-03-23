#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/Theme.py
-Single source of truth for all visual values across the entire app.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtGui import QColor, QPixmap, QPainter, QBrush
from pathlib import Path


class Theme:

    # =========================================================================
    # GLOBAL
    # =========================================================================

    windowBg            = "#282828"     # Primary window background
    primaryBorder       = "#6b5a47"     # Most lines and borders across the UI
    textPrimary         = "#d2d1cf"     # Ivory/warm white — labels, general text
    backDrop            = "#2a2a3a"     # Component background — canvas, dropdowns
    windowBorderWidth   = 1
    toolbarBorder       = primaryBorder
    layoutMargins       = (10, 5, 10, 5)
    handleHeightTop     = 35            # Top toolbar height — also the draggable area
    handleHeightBottom  = 100           # Bottom toolbar height

    # Sidebar
    sidebarPadding      = 6             # Padding inside the sidebar around buttons
    sidebarButtonGap    = 6             # Gap between buttons in the sidebar
    sidebarCategoryGap  = 16            # Gap between category groups
    # Sidebar width derives from iconButtonSize — single source, no magic numbers
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

    buttonBg                 = buttonPrimaryColor
    buttonBgHover            = buttonPrimaryColor
    buttonBgInactive         = buttonInactiveColor
    buttonBorder             = primaryBorder
    buttonBorderHover        = primaryBorder
    buttonBorderInactive     = buttonInactiveColor

    # --- Icon-only button (toolbar) ---
    iconButtonSize           = handleHeightTop - 3
    iconPadding              = 12

    # =========================================================================
    # FILES — all asset filenames declared in one place
    # =========================================================================
    # UI chrome icons are loaded via Theme.icon(Theme.iconXxx) which resolves
    # to the icons/ folder at the project root. Adding a new icon means adding
    # its filename constant here and calling Theme.icon() at the callsite.

    iconPathCurtains         = "iconic.png"         # Top toolbar curtain toggle button
    iconDelete               = "tester.png"         # Node delete (normal state)
    iconConfirm              = "icon_confirm.png"   # Node delete (confirm state)

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
    # NODES — BaseNode and all subclasses
    # =========================================================================

    nodeBg                  = "#2a2a2a"
    nodeBorder              = primaryBorder
    nodeBorderSelected      = textPrimary
    nodeBorderWidth         = 1.5
    nodeBorderSelectedScale = 1.8
    nodeRoundRadius         = 12.0
    nodeShadowBlur          = 28
    nodeShadowColor         = "#5a000000"   # ARGB hex — 35% black
    nodeShadowOffsetX       = 0
    nodeShadowOffsetY       = 4
    nodeShadowMargin        = 40
    nodeMinWidth            = 120.0
    nodeMinHeight           = 50.0
    nodeResizeGrip          = 16

    # Pulse animation
    nodePulseScale          = 1.018
    nodePulseMinMs          = 800
    nodePulseMaxMs          = 1400

    # =========================================================================
    # BEZIER NODE
    # =========================================================================

    bezierCurveColor        = "#a89a8a"     # Warm muted — resting curve
    bezierCurveColorSel     = "#d2d1cf"     # Brighter when selected
    bezierCurveWidth        = 2.5
    bezierHandleColor       = "#6b5a47"     # Handle fill
    bezierHandleHover       = "#d2d1cf"     # Handle on hover
    bezierArmColor          = "#4a3d33"     # Control arm line
    bezierArmWidth          = 1.0
    bezierHandleRadius      = 6.0

    # =========================================================================
    # HEALTH NODE
    # =========================================================================

    healthNodeBg            = "#1e2230"     # Slightly cooler than canvas — diagnostic feel
    healthNodeWidth         = 260.0
    healthNodeHeight        = 230.0

    healthColorLabel        = "#a89a8a"     # Muted warm — secondary labels
    healthColorCalm         = "#8cbea0"     # Mint green — delta 0, all clear
    healthColorWarn         = "#d4a96a"     # Amber — elevated node count
    healthColorHigh         = "#c97b7b"     # Rose — high node count, worth investigating
    healthWarnThreshold     = 50
    healthHighThreshold     = 150
    healthPollIntervalMs    = 2000

    healthFontFamily        = "Segoe UI"
    healthFontSizeLabel     = 8
    healthFontSizeValue     = 9
    healthFontSizeHeader    = 10
    healthFontSizeFooter    = 7


    # =========================================================================
    # ICON CACHE
    # =========================================================================
    # QPixmap objects are loaded once and reused everywhere.
    # Sharing the same QPixmap instance shares the underlying GPU texture —
    # zero duplicate loads, zero duplicate memory, zero duplicate GPU uploads.
    # All icon access goes through Theme.icon() — never load a QPixmap directly.

    _icon_cache: dict = {}   # filename → QPixmap, populated on first request

    @classmethod
    def icon(cls, filename: str, fallback_color: str = "#6b5a47") -> QPixmap:
        """
        Return the cached QPixmap for filename, loading it on first request.

        Looks in an icons/ folder at the project root (two levels up from
        this file). If the file is missing or fails to load, a plain filled
        circle in fallback_color is generated and cached instead — so the
        layout always holds without requiring assets to be present.

        Args:
            filename:       PNG filename, e.g. "icon_delete.png"
            fallback_color: Hex color for the generated fallback circle.
        """
        if filename in cls._icon_cache:
            return cls._icon_cache[filename]

        icon_path = Path(__file__).parent.parent / "icons" / filename
        pix = None

        if icon_path.exists():
            candidate = QPixmap(str(icon_path))
            if not candidate.isNull():
                pix = candidate

        if pix is None:
            # Generate fallback circle — visible so missing icons are obvious
            size = 32
            pix  = QPixmap(size, size)
            pix.fill(QColor(0, 0, 0, 0))
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QBrush(QColor(fallback_color)))
            p.setPen(QColor(fallback_color))
            p.drawEllipse(2, 2, size - 4, size - 4)
            p.end()

        cls._icon_cache[filename] = pix
        return pix

    # =========================================================================
    # UTILITIES
    # =========================================================================

    @staticmethod
    def to_hex(color) -> str:
        """
        Dev utility — convert a QColor to its HexArgb string.
        Not called at runtime in normal operation.
        Requires QColor to be imported at the callsite.
        """
        return color.name(QColor.HexArgb)

    @staticmethod
    def color(hex_str: str) -> QColor:
        """Convenience — construct a QColor from a Theme hex string on demand."""
        return QColor(hex_str)
