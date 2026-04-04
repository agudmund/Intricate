#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/InfoNode.py InfoNode class
-A read-only display node showing version, era, and app identity for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QFontMetrics, QColor

from nodes.BaseNode import BaseNode
from data.InfoNodeData import InfoNodeData
from graphics.Theme import Theme


class InfoNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = False
    """
    Read-only node that displays app version and era.

    No editor, no editing — just a painted label that always
    reflects the current __version__ and __era__ from main.py.
    """

    _BODY_LINES = [
        "A Gentle nodal space",
        "Where thoughts interlink ideas",
        "Transitioning Thoughts to Things",
        "",
        "A Creative Space",
        "Where the next breath of air found us",
        "Roaming free finding room to grow",
        "And become all that it could be",
        "",
        "Built by Yours Truly and Various Intelligences",
        "",
        "    For enjoying",
    ]

    def __init__(self, data: InfoNodeData | None = None):
        if data is None:
            data = InfoNodeData()

        # Auto-size width from widest body line + padding
        from main import __version__, __era__
        body_font = QFont("Lato", max(1, Theme.aboutFontSize - 1))
        fm = QFontMetrics(body_font)
        all_lines = [f"Version {__version__}", __era__] + self._BODY_LINES
        max_w = max(fm.horizontalAdvance(line) for line in all_lines)
        data.width = max(data.width, max_w + 30)

        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    def paint_content(self, painter: QPainter) -> None:
        from main import __version__, __era__

        painter.save()
        r = self.rect()
        pad = 15.0
        top = 24.0   # just below button zone

        # Title
        title_font = QFont("Chandler42", max(1, Theme.aboutFontSize + 6))
        painter.setFont(title_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, 40),
            Qt.AlignLeft | Qt.AlignTop,
            "Intricate",
        )

        # Version + Era
        body_font = QFont("Lato", max(1, Theme.aboutFontSize - 1))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.85)
        y = r.top() + top + 52
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            f"Version {__version__}",
        )
        y += 18
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            __era__,
        )

        # Description
        y += 28
        for line in self._BODY_LINES:
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                line,
            )
            y += 16

        painter.restore()

    def to_dict(self) -> dict:
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'InfoNode':
        return InfoNode(InfoNodeData.from_dict(d))
