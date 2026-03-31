#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Theme.py Theme class
-Live view over settings.toml. Colors, icons, and QPixmap caching for enjoying
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
        # Guard: only intercept iconXxx attributes — not the icon() method itself
        # or any other short name that happens to start with "icon".
        # A dynamic icon attribute is always "icon" + at least one more character
        # that is uppercase (camelCase convention from the TOML key transform).
        if name.startswith("icon") and len(name) > 4 and name[4].isupper():
            return _MISSING_ICON
        raise AttributeError(
            f"type object 'Theme' has no attribute '{name}'"
        )


class Theme(metaclass=_ThemeMeta):
    """
    Single source of truth for all visual values across the entire app family.

    Values flow in one direction:
        settings.toml → utils/settings.py → Theme → every widget and node

    Theme never writes to settings.toml directly — that's The Settlers' job.
    When settings.toml changes, settings.py calls Theme.reload() which pulls
    new values in and clears the icon cache so repaints pick up changes
    automatically.

    Hardcoded values here are structural constants only — things that are
    genuinely not user-configurable and have no reason to live in a config
    file (animation physics, minimum sizes, padding ratios). Everything the
    user might want to change lives in settings.toml.
    """



    # =========================================================================
    # GLOBAL — sourced from [theme.colors] in settings.toml
    # =========================================================================
    # Populated by reload() at startup and on every file change.
    # Accessing before reload() runs returns the hardcoded fallback below.

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
    buttonTextHover      = "#ffffff"

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
    nodeBorderSelected      = "#8a7560"
    nodeBorderWidth         = 1.0
    nodeBorderSelectedScale = 1.0
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
    nodeFontVerticalOffset  = -8.0
    nodeTextPaddingLeft     = 15.0
    nodeTextPaddingTop      = 4.0

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

    # =========================================================================
    # PERF NODE
    # =========================================================================

    perfNodeBg     = "#1a2020"
    perfNodeWidth  = 260.0
    perfNodeHeight = 240.0

    claudeBgColor            = windowBg
    claudeBgColorFront       = "#2a2a2a"
    claudeBgColorBack        = windowBg
    claudeBgColorInput       = "#2a2a2a"
    claudeBgAlpha            = 179
    claudeBodyFontFamily     = "Lato"
    claudeBodyFontSize       = 10
    claudeDefaultWidth       = 400.0
    claudeDefaultHeight      = 300.0
    claudeBorderWidth        = 1.0
    claudeBodyShowIcon       = "claude_body_show.png"
    claudeBodyHideIcon       = "claude_body_hide.png"
    imageVisionIcon          = "image_icon.png"

    wireStart                = "#7a9e8a"   # output port mint
    wireEnd                  = "#a07a5a"   # input port amber

    aboutFontFamily          = "Chandler42"
    aboutFontSize            = 10
    aboutFontColor           = "#e8f0ff"
    aboutBgColor             = "#2a2a2a"
    aboutBgColorFront        = "#322a3a"
    aboutBgAlpha             = 180
    aboutBorderColor         = "#6b5a47"
    aboutBorderHoverColor    = "#8a7560"
    aboutBorderSelectedColor = "#8a7560"
    aboutDepthIconOff        = "depth_off.png"
    aboutDepthIconOn         = "depth_on.png"
    portsIconOff             = "ports_off.png"
    portsIconOn              = "ports_on.png"
    aboutMinHeight           = 42.0
    aboutTextPaddingLeft     = 6.0
    aboutTextPaddingTop      = 0.0
    aboutFontVerticalOffset   = 0.0
    aboutEditorVerticalOffset = 0.0
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
            2. $SingleSharedBraincell_AssetVault/icons/ — personal asset vault.

        Local always wins over the vault so per-project overrides are respected.
        Returns None if the file is not found in either location.
        """
        import sys as _sys
        from utils.logger import TRACE

        # 1. Local / bundled icons/ — checked first.
        #    --onefile bundles extract to sys._MEIPASS; __file__ there resolves
        #    correctly relative to that temp dir so the same path expression works
        #    for both dev and frozen.  When frozen we also try sys._MEIPASS directly
        #    as a belt-and-suspenders guard against any __file__ resolution quirk.
        if getattr(_sys, "_MEIPASS", None):
            bundled = Path(_sys._MEIPASS) / "icons" / filename
            _log.log(TRACE, f"[icon resolve] '{filename}' → checking bundle: {bundled}")
            if bundled.exists():
                _log.debug(f"[icon resolve] '{filename}' → found in bundle: {bundled}")
                return bundled

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
    def from_hex(cls, hex_str: str, alpha: int = 255) -> 'QColor':
        """Create a QColor from a hex string with optional alpha (0-255)."""
        c = QColor(hex_str)
        c.setAlpha(alpha)
        return c

    @classmethod
    def icon(cls, filename: str | None, fallback_color: str = "#6b5a47") -> QPixmap:
        """
        Return the cached QPixmap for filename, loading on first request.

        Resolution order:
            1. ./icons/filename                                    — local override
            2. $SingleSharedBraincell_AssetVault/icons/filename   — personal vault
            3. _make_circle()                                      — honest fallback

        If filename is None, empty, or the _MISSING_ICON sentinel — skips
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
        Called by reload() when settings.toml reports a new icon path.
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
            1. Read colors from [theme.colors]  — update class attributes
            2. Read icons from [theme.icons]    — update filename attributes dynamically
            3. Clear icon cache for any filename that changed
            4. Dependent attributes (combobox colors etc.) recalculated
               from the new base values
        """
        # ── Base node ─────────────────────────────────────────────────────────
        node = settings.get_section("node")
        if "font_vertical_offset" in node:
            cls.nodeFontVerticalOffset = float(node["font_vertical_offset"])
        if "text_padding_left" in node:
            cls.nodeTextPaddingLeft = float(node["text_padding_left"])
        if "text_padding_top" in node:
            cls.nodeTextPaddingTop = float(node["text_padding_top"])
        if "border_selected_color" in node:
            cls.nodeBorderSelected = node["border_selected_color"]

        # ── Claude node ───────────────────────────────────────────────────────
        claude = settings.get_section("node").get("claude", {})
        cls.claudeBgColor      = claude.get("bg_color",       cls.windowBg)
        cls.claudeBgColorFront = claude.get("bg_color_front", cls.claudeBgColorFront)
        cls.claudeBgColorBack  = claude.get("bg_color_back",  cls.claudeBgColorBack)
        cls.claudeBgColorInput = claude.get("bg_color_input", cls.claudeBgColorInput)
        if "bg_alpha" in claude:
            cls.claudeBgAlpha = int(claude["bg_alpha"])
        if "body_font_family" in claude:
            cls.claudeBodyFontFamily = claude["body_font_family"]
        if "body_font_size" in claude:
            cls.claudeBodyFontSize = int(claude["body_font_size"])
        if "default_width" in claude:
            cls.claudeDefaultWidth = float(claude["default_width"])
        if "default_height" in claude:
            cls.claudeDefaultHeight = float(claude["default_height"])
        if "border_width" in claude:
            cls.claudeBorderWidth = float(claude["border_width"])

        # ── About node ────────────────────────────────────────────────────────
        # Inherit base node offsets first — [node.about] overrides only what it explicitly sets.
        cls.aboutFontVerticalOffset = cls.nodeFontVerticalOffset
        cls.aboutTextPaddingLeft    = cls.nodeTextPaddingLeft
        cls.aboutTextPaddingTop     = cls.nodeTextPaddingTop
        about = settings.get_section("node").get("about", {})
        if "font_size" in about:
            cls.aboutFontSize = int(about["font_size"])
        if "font_color" in about:
            cls.aboutFontColor = about["font_color"]
        if "bg_color" in about:
            cls.aboutBgColor = about["bg_color"]
        if "bg_color_front" in about:
            cls.aboutBgColorFront = about["bg_color_front"]
        if "bg_alpha" in about:
            cls.aboutBgAlpha = int(about["bg_alpha"])
        if "border_color" in about:
            cls.aboutBorderColor = about["border_color"]
        if "border_hover_color" in about:
            cls.aboutBorderHoverColor = about["border_hover_color"]
        if "border_selected_color" in about:
            cls.aboutBorderSelectedColor = about["border_selected_color"]
        if "depth_icon_off" in about:
            cls.aboutDepthIconOff = about["depth_icon_off"]
        if "depth_icon_on" in about:
            cls.aboutDepthIconOn = about["depth_icon_on"]
        if "min_height" in about:
            cls.aboutMinHeight = float(about["min_height"])
        if "text_padding_left" in about:
            cls.aboutTextPaddingLeft = float(about["text_padding_left"])
        if "text_padding_top" in about:
            cls.aboutTextPaddingTop = float(about["text_padding_top"])
        if "font_vertical_offset" in about:
            cls.aboutFontVerticalOffset = float(about["font_vertical_offset"])
        if "editor_vertical_offset" in about:
            cls.aboutEditorVerticalOffset = float(about["editor_vertical_offset"])

        # ── Colors ────────────────────────────────────────────────────────────
        colors = settings.get_section("theme").get("colors", {})

        if "window_bg" in colors:
            cls.windowBg           = colors["window_bg"]
            cls.toolbarBg          = cls.windowBg
            cls.buttonPrimaryColor = cls.windowBg
            cls.buttonBg           = cls.windowBg
            cls.buttonBgHover      = cls.windowBg
            cls.comboboxBg         = cls.windowBg

        if "primary_border" in colors:
            cls.primaryBorder     = colors["primary_border"]
            cls.toolbarBorder     = cls.primaryBorder
            cls.buttonBorder      = cls.primaryBorder
            cls.buttonBorderHover = cls.primaryBorder
            cls.nodeBorder        = cls.primaryBorder
            cls.comboboxBorder    = cls.primaryBorder
            cls.bezierHandleColor = cls.primaryBorder

        if "text_primary" in colors:
            cls.textPrimary        = colors["text_primary"]
            cls.comboboxText       = cls.textPrimary

        if "backdrop" in colors:
            cls.backDrop       = colors["backdrop"]
            cls.comboboxBgOpen = cls.backDrop

        # ── Icons ─────────────────────────────────────────────────────────────
        # Fully dynamic — no closed icon_map. Every key present in [theme.icons]
        # becomes a Theme attribute automatically:
        #   "curtains" → Theme.iconCurtains
        #   "close"    → Theme.iconClose
        #   "anything" → Theme.iconAnything
        #
        # Attribute naming: "icon" + first char uppercased + rest preserved as-is.
        # This keeps camelCase keys intact:
        #   "healthBig" → Theme.iconHealthBig  (not Theme.iconHealthbig)
        #
        # If a key is present in the TOML with an empty value, or was present
        # in a previous load but is now absent, the attribute is removed so the
        # metaclass __getattr__ returns _MISSING_ICON and Theme.icon() draws a
        # circle — consistent with a key that was never set at all.
        icons = settings.get_section("theme").get("icons", {})

        # Track previously dynamic attrs so we can clean up keys removed from TOML
        # existing_dynamic = {
            # k for k in vars(cls)
            # if k.startswith("icon") and k not in (
            #     "iconButtonSize", "iconPadding", "iconSize",
            #     "_icon_cache", "invalidate_icon", "invalidate_all_icons"
            # )
        # }
        existing_dynamic = {k for k in vars(cls)}

        seen_attrs = set()
        for toml_key, filename in icons.items():
            attr_name = "icon" + toml_key[0].upper() + toml_key[1:]
            seen_attrs.add(attr_name)
            old_filename = getattr(cls, attr_name, None)

            if filename:
                # Key present and non-empty — update if changed
                if old_filename != filename:
                    cls.invalidate_icon(old_filename or "")
                    setattr(cls, attr_name, filename)
            else:
                # Empty value — invalidate cache and remove attribute so next
                # paint gets the circle fallback, same as if the key never existed
                if old_filename:
                    cls.invalidate_icon(old_filename)
                try:
                    delattr(cls, attr_name)
                except AttributeError:
                    pass

        # Remove dynamic icon attrs for keys that disappeared from the TOML entirely
        # for attr_name in existing_dynamic - seen_attrs:
        #     old_filename = getattr(cls, attr_name, None)
            # if old_filename:
            #     cls.invalidate_icon(old_filename)
            # try:
            #     delattr(cls, attr_name)
            # except AttributeError:
            #     pass

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
