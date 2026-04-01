#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/PaletteNode.py PaletteNode class
-A swatch board: collect hex values and see their colors side by side for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QFrame, QPushButton, QScrollArea, QLabel,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor

from nodes.BaseNode import BaseNode
from data.PaletteNodeData import PaletteNodeData
from graphics.Theme import Theme


PADDING      = 6.0
TITLE_GAP    = 4.0
SWATCH_W     = 110
SWATCH_H     = 70
CELL_SPACING = 10
COLUMNS      = 2


# ─────────────────────────────────────────────────────────────────────────────
# SWATCH CELL  — one color entry: label, swatch box, hex value
# ─────────────────────────────────────────────────────────────────────────────

class _SwatchCell(QWidget):
    """
    Single palette entry.

    Layout (top to bottom):
        editable label   — human description ("Background", "Border" …)
        color swatch     — large outlined rectangle
        editable hex     — color value ("#363646")
    """

    def __init__(self, label: str, hex_color: str, on_change, on_remove):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # ── Label ─────────────────────────────────────────────────────────────
        self._label = QLineEdit(label)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(f"""
            QLineEdit {{
                background:  transparent;
                color:       {Theme.textPrimary};
                border:      none;
                font-family: 'Chandler42';
                font-size:   8pt;
                padding:     0;
            }}
        """)
        layout.addWidget(self._label)

        # ── Swatch ────────────────────────────────────────────────────────────
        self._swatch = QFrame()
        self._swatch.setFixedSize(SWATCH_W, SWATCH_H)
        self._update_swatch(hex_color)
        layout.addWidget(self._swatch, 0, Qt.AlignHCenter)

        # ── Hex input ─────────────────────────────────────────────────────────
        self._hex = QLineEdit(hex_color)
        self._hex.setAlignment(Qt.AlignCenter)
        self._hex.setMaxLength(9)
        self._hex.setStyleSheet(f"""
            QLineEdit {{
                background:  transparent;
                color:       {Theme.textPrimary};
                border:      none;
                font-family: 'Chandler42';
                font-size:   8pt;
                padding:     0;
            }}
        """)
        layout.addWidget(self._hex)

        # ── Remove button (subtle, top-right) ────────────────────────────────
        self._rm_btn = QPushButton("×")
        self._rm_btn.setFixedSize(16, 16)
        self._rm_btn.setCursor(Qt.PointingHandCursor)
        self._rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color:      {Theme.primaryBorder};
                border:     none;
                font-size:  10pt;
                padding:    0;
            }}
            QPushButton:hover {{ color: {Theme.nodeBorderSelected}; }}
        """)
        self._rm_btn.setParent(self)
        self._rm_btn.move(self.width() - 18, 2)
        self._rm_btn.clicked.connect(lambda: on_remove(self))
        self._rm_btn.hide()

        # ── Signals ───────────────────────────────────────────────────────────
        self._hex.textChanged.connect(self._on_hex_changed)
        self._hex.textChanged.connect(lambda _: on_change())
        self._label.textChanged.connect(lambda _: on_change())

    def _on_hex_changed(self, text: str) -> None:
        c = QColor(text)
        if c.isValid():
            self._update_swatch(text)

    def _update_swatch(self, hex_color: str) -> None:
        self._swatch.setStyleSheet(
            f"background: {hex_color};"
            f"border: 1px solid {Theme.primaryBorder};"
            f"border-radius: 4px;"
        )

    def enterEvent(self, event):
        self._rm_btn.move(self.width() - 18, 2)
        self._rm_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._rm_btn.hide()
        super().leaveEvent(event)

    def get_data(self) -> dict:
        return {"label": self._label.text(), "hex": self._hex.text()}


# ─────────────────────────────────────────────────────────────────────────────
# PALETTE WIDGET  — scrollable 2-up grid of swatch cells
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteWidget(QWidget):

    def __init__(self, colors: list, on_change):
        super().__init__()
        self._on_change = on_change
        self._cells: list[_SwatchCell] = []

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 5px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.primaryBorder}; border-radius: 2px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._container = QWidget()
        self._container.setAttribute(Qt.WA_TranslucentBackground)
        self._container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(CELL_SPACING)
        self._grid.setVerticalSpacing(CELL_SPACING)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        # ── Add button ────────────────────────────────────────────────────────
        add_btn = QPushButton("+ add color")
        add_btn.setFixedHeight(22)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background:    transparent;
                color:         {Theme.textPrimary};
                border:        1px solid {Theme.primaryBorder};
                border-radius: 4px;
                font-family:   'Chandler42';
                font-size:     8pt;
                padding:       0 6px;
            }}
            QPushButton:hover {{
                border-color: {Theme.nodeBorderSelected};
                color:        {Theme.nodeBorderSelected};
            }}
        """)
        add_btn.clicked.connect(lambda: self.add_color())
        outer.addWidget(add_btn)

        for c in colors:
            self._append_cell(c.get("label", "Color"), c.get("hex", "#888888"))

    # ── Cell management ───────────────────────────────────────────────────────

    def _append_cell(self, label: str, hex_color: str) -> None:
        cell = _SwatchCell(label, hex_color, self._fire_change, self._remove_cell)
        self._cells.append(cell)
        self._relayout()

    def _remove_cell(self, cell: _SwatchCell) -> None:
        if cell in self._cells:
            self._cells.remove(cell)
            cell.setParent(None)
            cell.deleteLater()
            self._relayout()
            self._fire_change()

    def _relayout(self) -> None:
        # Clear grid without destroying widgets
        while self._grid.count():
            self._grid.takeAt(0)
        for i, cell in enumerate(self._cells):
            row = i // COLUMNS
            col = i %  COLUMNS
            self._grid.addWidget(cell, row, col, Qt.AlignTop)

    def _fire_change(self) -> None:
        self._on_change(self.get_colors())

    def add_color(self, label: str = "Color", hex_color: str = "#c0a888") -> None:
        self._append_cell(label, hex_color)
        self._fire_change()

    # ── Data access ───────────────────────────────────────────────────────────

    def get_colors(self) -> list:
        return [cell.get_data() for cell in self._cells]

    def set_colors(self, colors: list) -> None:
        for cell in list(self._cells):
            cell.setParent(None)
            cell.deleteLater()
        self._cells.clear()
        for c in colors:
            self._append_cell(c.get("label", "Color"), c.get("hex", "#888888"))


# ─────────────────────────────────────────────────────────────────────────────
# PALETTE NODE
# ─────────────────────────────────────────────────────────────────────────────

class PaletteNode(BaseNode):
    """
    A swatch board for collecting and editing hex colors.

    Each cell shows a label, a large color swatch, and an editable hex field.
    Colors are arranged in a 2-column grid matching the Photoshop palette style.
    """

    def __init__(self, data: PaletteNodeData | None = None):
        if data is None:
            data = PaletteNodeData()
        super().__init__(data)

        self._palette: _PaletteWidget | None = None
        self._palette_proxy: QGraphicsProxyWidget | None = None
        self._build_palette_view()

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _body_rect(self) -> QRectF:
        r   = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + TITLE_GAP + PADDING
        return QRectF(
            r.x()  + PADDING,
            top,
            r.width()  - PADDING * 2,
            r.height() - (top - r.y()) - PADDING,
        )

    def _build_palette_view(self) -> None:
        self._palette = _PaletteWidget(
            colors    = list(self.data.colors),
            on_change = self._on_colors_changed,
        )
        self._palette_proxy = QGraphicsProxyWidget(self)
        self._palette_proxy.setWidget(self._palette)
        self._palette_proxy.setGeometry(self._body_rect())
        self._palette_proxy.show()

    def _on_colors_changed(self, colors: list) -> None:
        self.data.colors = colors

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # RESIZE
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if self._palette_proxy:
            self._palette_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._palette_proxy:
            self._palette_proxy.hide()
        self._palette = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        if self._palette:
            self.data.colors = self._palette.get_colors()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PaletteNode':
        return PaletteNode(PaletteNodeData.from_dict(data))
