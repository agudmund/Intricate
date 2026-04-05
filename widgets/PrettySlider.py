#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Slider
-The last of the pretty sliders knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider

from graphics.Theme import Theme
import utils.settings as settings


class PrettySlider(QSlider):
    """
    A themed QSlider that matches the ghost scrollbar aesthetic of the app.

    Pill-shaped handle in Theme.primaryBorder, transparent groove on both
    sides, Theme.textPrimary on hover.  Orientations:

        Vertical   — groove 4px wide,  handle 14×18px, centred in a 30px lane.
        Horizontal — groove 4px tall,  handle 18×14px, centred in a 20px lane.

    Pass use_scroll_icon=True to substitute the pill with the custom PNG
    configured in settings.toml [theme.icons] scroll_handle.  Works for both
    orientations — margins are computed from the image's actual pixel
    dimensions so the handle always centres correctly on the 4px groove.
    Falls back to the pill if no icon is configured.
    """

    _GROOVE_PX  = 4   # groove thickness (px) — shared by both orientations
    _HANDLE_PX  = 16  # target rendered size for PNG handle icons (px, both axes)

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        use_scroll_icon: bool = False,
        parent=None,
    ):
        super().__init__(orientation, parent)
        self._use_scroll_icon = use_scroll_icon
        self._apply_stylesheet()

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(self._build_stylesheet())

    def _build_stylesheet(self) -> str:
        if self.orientation() == Qt.Orientation.Vertical:
            return self._vertical_stylesheet()
        return self._horizontal_stylesheet()

    def _vertical_stylesheet(self) -> str:
        handle = self._png_handle_block(Qt.Orientation.Vertical) or f"""
            QSlider::handle:vertical {{
                background:    {Theme.primaryBorder};
                border:        none;
                width:         14px;
                height:        18px;
                border-radius: 4px;
                margin:        0px -5px;
            }}
            QSlider::handle:vertical:hover {{
                background:    {Theme.textPrimary};
            }}"""
        return f"""
            QSlider::groove:vertical {{
                background:    transparent;
                width:         {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        0px 13px;
            }}
            {handle}
            QSlider::add-page:vertical {{
                background:    transparent;
                width:         {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        0px 13px;
            }}
            QSlider::sub-page:vertical {{
                background:    transparent;
                width:         {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        0px 13px;
            }}
        """

    def _horizontal_stylesheet(self) -> str:
        # Groove margin centres the 4px track vertically in the slider lane.
        # Lane height is fixed at 20px → (20 - 4) / 2 = 8px top/bottom.
        handle = self._png_handle_block(Qt.Orientation.Horizontal) or f"""
            QSlider::handle:horizontal {{
                background:    {Theme.primaryBorder};
                border:        none;
                width:         18px;
                height:        14px;
                border-radius: 4px;
                margin:        -5px 0px;
            }}
            QSlider::handle:horizontal:hover {{
                background:    {Theme.textPrimary};
            }}"""
        return f"""
            QSlider::groove:horizontal {{
                background:    transparent;
                height:        {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        8px 0px;
            }}
            {handle}
            QSlider::add-page:horizontal {{
                background:    transparent;
                height:        {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        8px 0px;
            }}
            QSlider::sub-page:horizontal {{
                background:    transparent;
                height:        {self._GROOVE_PX}px;
                border-radius: 2px;
                margin:        8px 0px;
            }}
        """

    # ── PNG handle helper ─────────────────────────────────────────────────────

    def _png_handle_block(self, orientation: Qt.Orientation) -> str | None:
        """
        Build a QSS handle block for the configured scroll-handle PNG icon.

        Returns None when use_scroll_icon is False or no icon is configured,
        so callers can fall back to the pill style with a simple ``or``.

        The icon is rendered at _HANDLE_PX × _HANDLE_PX regardless of the
        PNG's natural pixel dimensions — Qt scales image: to the specified
        width/height in QSS, so oversized source files don't blow up the UI.
        Margins are computed from _HANDLE_PX so the handle is always centred
        on the _GROOVE_PX groove:

            side_margin = -(_HANDLE_PX / 2 - _GROOVE_PX / 2)

        Example — _HANDLE_PX=16, _GROOVE_PX=4:
            side_margin = -(8 - 2) = -6px  →  centred correctly in both axes.
        """
        if not self._use_scroll_icon:
            return None
        icon_filename = settings.get_nested("theme", "sliders", "slider_handle_icon", None)
        if not icon_filename:
            return None
        path = Theme._resolve_icon_path(icon_filename)
        if not path:
            return None

        url         = str(path).replace("\\", "/")
        size        = int(settings.get_nested("theme", "sliders", "slider_handle_size", self._HANDLE_PX))
        side_margin = -(size // 2 - self._GROOVE_PX // 2)

        if orientation == Qt.Orientation.Vertical:
            return f"""
                QSlider::handle:vertical {{
                    image:  url({url});
                    width:  {size}px;
                    height: {size}px;
                    margin: 0px {side_margin}px;
                }}"""
        else:
            return f"""
                QSlider::handle:horizontal {{
                    image:  url({url});
                    width:  {size}px;
                    height: {size}px;
                    margin: {side_margin}px 0px;
                }}"""


    # ── Handle tinting for HoverGlow ────────────────────────────────────────

    _base_handle_pixmap = None   # cached original PNG
    _tint_path = None            # temp file path for tinted image

    def set_handle_tint(self, color_hex: str) -> None:
        """Tint the handle icon's opaque pixels to *color_hex* and refresh.

        Uses CompositionMode_SourceAtop so only opaque pixels are recolored —
        the alpha channel is preserved exactly as-is.  The tinted image is
        written to a temp file that the QSS ``image:`` property references.
        """
        from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
        import tempfile, os

        # Resolve and cache the original handle PNG
        if self._base_handle_pixmap is None:
            icon_filename = settings.get_nested("theme", "sliders", "slider_handle_icon", None)
            if not icon_filename:
                return
            path = Theme._resolve_icon_path(icon_filename)
            if not path:
                return
            self._base_handle_pixmap = QPixmap(str(path))
            if self._base_handle_pixmap.isNull():
                self._base_handle_pixmap = None
                return
            # Stable temp file — reused every frame, cleaned up on exit
            fd, self._tint_path = tempfile.mkstemp(suffix=".png", prefix="intricate_handle_")
            os.close(fd)

        # Tint: paint color over opaque pixels only
        tinted = QPixmap(self._base_handle_pixmap)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.fillRect(tinted.rect(), QColor(color_hex))
        painter.end()

        tinted.save(self._tint_path, "PNG")

        # Rebuild stylesheet with the tinted image path
        url = self._tint_path.replace("\\", "/")
        size = int(settings.get_nested("theme", "sliders", "slider_handle_size", self._HANDLE_PX))
        side_margin = -(size // 2 - self._GROOVE_PX // 2)

        if self.orientation() == Qt.Orientation.Vertical:
            handle_block = f"""
                QSlider::handle:vertical {{
                    image:  url({url});
                    width:  {size}px;
                    height: {size}px;
                    margin: 0px {side_margin}px;
                }}"""
            groove_key = "vertical"
        else:
            handle_block = f"""
                QSlider::handle:horizontal {{
                    image:  url({url});
                    width:  {size}px;
                    height: {size}px;
                    margin: {side_margin}px 0px;
                }}"""
            groove_key = "horizontal"

        gm = "8px 0px" if groove_key == "horizontal" else "0px 13px"
        self.setStyleSheet(f"""
            QSlider::groove:{groove_key} {{
                background: transparent;
                {"height" if groove_key == "horizontal" else "width"}: {self._GROOVE_PX}px;
                border-radius: 2px;
                margin: {gm};
            }}
            {handle_block}
            QSlider::add-page:{groove_key} {{
                background: transparent;
                {"height" if groove_key == "horizontal" else "width"}: {self._GROOVE_PX}px;
                border-radius: 2px;
                margin: {gm};
            }}
            QSlider::sub-page:{groove_key} {{
                background: transparent;
                {"height" if groove_key == "horizontal" else "width"}: {self._GROOVE_PX}px;
                border-radius: 2px;
                margin: {gm};
            }}
        """)


def slider(
    orientation: Qt.Orientation = Qt.Orientation.Horizontal,
    use_scroll_icon: bool = False,
    parent=None,
    **kwargs,
) -> PrettySlider:
    """
    Create a themed PrettySlider.

    Common kwargs:
        range        = (min, max)   → setRange(min, max)
        value        = int          → setValue(int)
        fixedHeight  = int          → setFixedHeight(int)
        fixedWidth   = int          → setFixedWidth(int)
        valueChanged = callable     → valueChanged.connect(callable)
        invertedAppearance = bool   → setInvertedAppearance(bool)
    """
    s = PrettySlider(orientation, use_scroll_icon=use_scroll_icon, parent=parent)

    if "range" in kwargs:
        lo, hi = kwargs.pop("range")
        s.setRange(lo, hi)

    if "valueChanged" in kwargs:
        slot = kwargs.pop("valueChanged")
        if slot:
            s.valueChanged.connect(slot)

    for key, value in kwargs.items():
        if not key:
            continue
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(s, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettySlider has no setter for '{key}' (tried {setter_name})")

    return s
