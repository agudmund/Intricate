#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/paint.py data-grid paint helpers
-Stateless draw dispatchers for the header→rows→footer grid used by monitor nodes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui  import QColor, QFont, QPainter, QPen


# ─────────────────────────────────────────────────────────────────────────────
# KIT — pre-resolved Qt objects, built once per paint pass
# ─────────────────────────────────────────────────────────────────────────────

class DataGridKit:
    """Pre-resolved fonts, colors, and pens for a data-grid paint pass."""
    __slots__ = (
        "f_label", "f_value", "f_header", "f_footer",
        "c_label", "c_header", "div_pen",
        "pad", "line_h",
    )

    def __init__(
        self,
        f_label:  QFont,
        f_value:  QFont,
        f_header: QFont,
        f_footer: QFont,
        c_label:  QColor,
        c_header: QColor,
        div_pen:  QPen,
        pad:      int = 12,
        line_h:   int = 18,
    ) -> None:
        self.f_label  = f_label
        self.f_value  = f_value
        self.f_header = f_header
        self.f_footer = f_footer
        self.c_label  = c_label
        self.c_header = c_header
        self.div_pen  = div_pen
        self.pad      = pad
        self.line_h   = line_h


def make_kit(
    title_font: str = "Chandler42",
    title_style: str = "MediumOblique",
    title_bump: int = 6,
) -> DataGridKit:
    """Read Theme once and return a fully resolved kit."""
    from pretty_widgets.graphics.Theme import Theme

    f_label = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel))
    f_value = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeValue))
    f_value.setBold(True)
    f_header = QFont(title_font, max(1, Theme.healthFontSizeHeader + title_bump))
    f_header.setStyleName(title_style)
    f_footer = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeFooter))

    c_label  = QColor(Theme.healthColorLabel)
    c_header = QColor("#72b8b8")  # Lombardi Lake variant
    div_pen  = QPen(QColor(Theme.primaryBorder), 1, Qt.DotLine)

    return DataGridKit(
        f_label=f_label,
        f_value=f_value,
        f_header=f_header,
        f_footer=f_footer,
        c_label=c_label,
        c_header=c_header,
        div_pen=div_pen,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DRAW FUNCTIONS — stateless, return updated y-cursor
# ─────────────────────────────────────────────────────────────────────────────

def draw_header(
    painter: QPainter,
    kit: DataGridKit,
    x: float, y: float, w: float,
    text: str,
) -> float:
    """Lombardi Lake header + dotted divider. Returns new y."""
    line_h = kit.line_h
    painter.setFont(kit.f_header)
    painter.setPen(kit.c_header)
    painter.drawText(int(x), int(y), int(w), line_h + 4,
                     Qt.AlignLeft | Qt.AlignVCenter, text)
    y += line_h + 6
    painter.setPen(kit.div_pen)
    painter.drawLine(int(x), int(y), int(x + w), int(y))
    y += 8
    return y


def draw_rows(
    painter: QPainter,
    kit: DataGridKit,
    x: float, y: float, w: float,
    rows: list[tuple[str, str, QColor]],
) -> float:
    """Label/value row loop — label left 60%, value right-aligned. Returns new y."""
    line_h  = kit.line_h
    f_label = kit.f_label
    f_value = kit.f_value
    c_label = kit.c_label
    lw      = int(w * 0.6)
    iw      = int(w)
    ix      = int(x)
    for label, value, value_color in rows:
        painter.setFont(f_label)
        painter.setPen(c_label)
        painter.drawText(ix, int(y), lw, line_h,
                         Qt.AlignLeft | Qt.AlignVCenter, label)
        painter.setFont(f_value)
        painter.setPen(value_color)
        painter.drawText(ix, int(y), iw, line_h,
                         Qt.AlignRight | Qt.AlignVCenter, value)
        y += line_h + 3
    return y


def draw_footer(
    painter: QPainter,
    kit: DataGridKit,
    x: float, y: float, w: float,
    text: str,
    gap: int = 2,
) -> float:
    """Dotted divider + centered footer text. Returns new y."""
    line_h = kit.line_h
    y += gap
    painter.setPen(kit.div_pen)
    painter.drawLine(int(x), int(y), int(x + w), int(y))
    y += 6
    painter.setFont(kit.f_footer)
    painter.setPen(kit.c_label)
    painter.drawText(int(x), int(y), int(w), line_h,
                     Qt.AlignCenter, text)
    y += line_h
    return y


def draw_hero(
    painter: QPainter,
    kit: DataGridKit,
    x: float, y: float, w: float,
    text: str,
    color: QColor,
    font_size: int = 16,
    height: int = 28,
) -> float:
    """Bold centered hero value + second divider. Returns new y."""
    hero_font = QFont(kit.f_value)  # copy to avoid mutating kit
    hero_font.setPointSize(max(1, font_size))
    hero_font.setBold(True)
    painter.setFont(hero_font)
    painter.setPen(color)
    painter.drawText(int(x), int(y), int(w), height,
                     Qt.AlignCenter | Qt.AlignVCenter, text)
    y += height + 4
    painter.setPen(kit.div_pen)
    painter.drawLine(int(x), int(y), int(x + w), int(y))
    y += 8
    return y
