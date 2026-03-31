#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Combo
-The last of the pretty combos knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QComboBox, QListView, QStyledItemDelegate, QStyleFactory, QVBoxLayout, QWidget
from graphics.Theme import Theme
import utils.settings as settings


class _TightDelegate(QStyledItemDelegate):
    """
    Overrides sizeHint so item height = font height + 2 * item_padding_v.
    Without this, QStyledItemDelegate adds its own internal style margins
    regardless of the stylesheet padding value.
    """
    def sizeHint(self, option, index):
        sh  = super().sizeHint(option, index)
        pad = int(settings.get_nested("theme", "combo", "list_padding_v", 4) or 0)
        return QSize(sh.width(), option.fontMetrics.height() + pad * 2)


class PrettyCombo(QComboBox):
    """
    A themed QComboBox matching the app's context-menu aesthetic.

    Closed state:  transparent background, no border, no arrow,
                   'My Olivin (Nabana)' 11px, Theme.primaryBorder text.
    Dropdown:      Theme.backDrop background, 1px primaryBorder border,
                   9px radius, 4px container padding — identical to QMenu.
    Items:         item_padding_v / item_padding_h from [theme.combo] in settings.toml.
    Selection:     pink-to-dark horizontal gradient (same as QMenu::item:selected).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Fusion style fully honours stylesheet border-radius and padding.
        # The Windows native style overrides both, leaving a plain tight box
        # regardless of what the stylesheet says.
        self.setStyle(QStyleFactory.create("Fusion"))
        # Replace the native OS popup with a plain QListView so Qt renders
        # the entire dropdown itself — stylesheet, font, and scrollbar all apply.
        self.setView(QListView())
        self.setItemDelegate(_TightDelegate(self))
        self._apply_stylesheet()
        if settings.watcher:
            settings.watcher.changed.connect(self.update_style)

    def _apply_stylesheet(self) -> None:
        # Closed combobox: text clearance inside the border
        closed_v  = int(settings.get_nested("theme", "combo", "closed_padding_v", 2) or 0)
        closed_h  = int(settings.get_nested("theme", "combo", "closed_padding_h", 8) or 0)
        # Closed combobox: how much the border frame grows beyond the font height
        border_v  = int(settings.get_nested("theme", "combo", "closed_border_v",  4) or 0)
        # Dropdown list item padding
        list_v    = int(settings.get_nested("theme", "combo", "list_padding_v", 4) or 0)
        list_h    = int(settings.get_nested("theme", "combo", "list_padding_h", 16) or 0)
        color     = settings.get("theme", "ui_label_color", "") or Theme.textPrimary
        font      = settings.get("theme", "ui_font",        "Lato")
        font_size = int(settings.get("theme", "ui_font_size", 11))
        # border_v drives the outer frame height independently of text clearance.
        # setFixedHeight clamps both min and max — stylesheet padding lives
        # inside this fixed height, not on top of it.
        fm      = QFontMetrics(QFont(font, font_size))
        min_h   = fm.height() + border_v * 2
        self.setMinimumHeight(min_h)
        self.setMaximumHeight(min_h)
        # Cap border-radius to half the height — Qt Fusion drops rounding
        # entirely if the radius exceeds half the widget's actual height.
        radius  = min(Theme.nodeRoundRadius, min_h / 2)
        self.setStyleSheet(
            f"""
            QComboBox {{
                background:    transparent;
                border:        1px solid {Theme.primaryBorder};
                border-radius: {radius}px;
                color:         {color};
                font-family:   '{font}';
                font-size:     {font_size}pt;
                padding:       0px {closed_h}px;
                min-height:    {min_h}px;
                max-height:    {min_h}px;
                margin:        0px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox::down-arrow {{ image: none; width: 0; }}
            QComboBox QAbstractItemView {{
                background:    {Theme.backDrop};
                color:         {Theme.textPrimary};
                border:        1px solid {Theme.primaryBorder};
                border-radius: 9px;
                padding:       4px;
                font-family:   'My Olivin (Nabana)';
                font-size:     11px;
                selection-background-color: transparent;
                outline:       0;
            }}
            QComboBox QAbstractItemView::item {{
                padding:       {list_v}px {list_h}px;
                border-radius: 5px;
                border:        none;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e1e1e, stop:0.4 #5c3e4f,
                    stop:0.7 #a56a85, stop:1 #d87a9e);
            }}
            QMenu {{
                background:    {Theme.backDrop};
                color:         {Theme.textPrimary};
                border:        1px solid {Theme.primaryBorder};
                border-radius: 9px;
                padding:       4px;
                font-family:   'My Olivin (Nabana)';
                font-size:     11px;
            }}
            QMenu::item {{
                padding:       5px 16px;
                border-radius: 5px;
            }}
            QMenu::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e1e1e, stop:0.4 #5c3e4f,
                    stop:0.7 #a56a85, stop:1 #d87a9e);
            }}
            QScrollBar:vertical {{
                background:   {Theme.backDrop};
                width:        6px;
                border-radius: 3px;
                margin:       0;
            }}
            QScrollBar::handle:vertical {{
                background:   {Theme.primaryBorder};
                border-radius: 3px;
                min-height:   20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )

    def showPopup(self) -> None:
        """Size the dropdown to fit the widest item text + list_padding_h on each side."""
        f = QFont("My Olivin (Nabana)")
        f.setPixelSize(11)   # match the stylesheet's 11px, not 11pt
        fm = QFontMetrics(f)
        max_text_w = max(
            (fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())),
            default=0,
        )
        list_h  = max(0, int(settings.get_nested("theme", "combo", "list_padding_h", 16) or 0))
        list_w_extra = int(settings.get_nested("theme", "combo", "list_width_extra", 20) or 0)
        popup_w = max_text_w + list_h * 2 + list_w_extra

        self.view().setFixedWidth(popup_w)
        super().showPopup()

    def update_style(self) -> None:
        """Re-apply stylesheet and refresh delegate after a theme reload."""
        self._apply_stylesheet()


class PrettyComboGroup(QWidget):
    """
    Container that stacks PrettyCombo widgets vertically, each left-aligned
    to its natural content width.  This prevents the parent layout from
    stretching combos to full column width, which eliminates the unstyled
    flash artifact when the popup opens.
    """

    def __init__(self, spacing: int = 2, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)
        self._combos: list[PrettyCombo] = []

    def add(self, c: PrettyCombo) -> PrettyCombo:
        self._layout.addWidget(c, 0, Qt.AlignmentFlag.AlignLeft)
        self._combos.append(c)
        return c

    def update_style(self) -> None:
        for c in self._combos:
            c.update_style()


def combo_group(spacing: int = 2, parent=None) -> PrettyComboGroup:
    """Create a PrettyComboGroup that left-aligns combos to their content width."""
    return PrettyComboGroup(spacing=spacing, parent=parent)


def combo(
    items: list[str] = None,
    parent=None,
    **kwargs,
) -> PrettyCombo:
    """
    Create a themed PrettyCombo.

    Common kwargs:
        currentIndex = int      → setCurrentIndex(int)
        fixedWidth   = int      → setFixedWidth(int)
        fixedHeight  = int      → setFixedHeight(int)
        currentIndexChanged = callable  → currentIndexChanged.connect(callable)
        activated           = callable  → activated.connect(callable)
    """
    c = PrettyCombo(parent=parent)

    if items:
        c.addItems(items)

    for signal_name in ("currentIndexChanged", "activated", "currentTextChanged"):
        if signal_name in kwargs:
            slot = kwargs.pop(signal_name)
            if slot:
                getattr(c, signal_name).connect(slot)

    for key, value in kwargs.items():
        if not key:
            continue
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(c, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettyCombo has no setter for '{key}' (tried {setter_name})")

    return c
