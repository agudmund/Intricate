#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/NullNode.py NullNode class
-The last of the null node chose a spot and stayed there, quietly anchoring whatever wanted to find it, For enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont

from nodes.BaseNode import BaseNode
from data.NullNodeData import NullNodeData
from pretty_widgets.graphics.Theme import Theme


class NullNode(BaseNode):
    """
    Transparent passthrough anchor.

    No content, no editor, no paint beyond a subtle crosshair.
    Just ports and a position you can wire into anything that needs
    a spatial reference point (BloomNode scatter origin, wire routing, etc.).
    """
    _has_depth_toggle = True

    def __init__(self, data: NullNodeData | None = None):
        if data is None:
            data = NullNodeData()
        # Ports visible by default — that's the whole point
        data.ports_visible = True
        super().__init__(data)

        self._apply_depth()

    def _bg_color(self) -> QColor:
        c = QColor(Theme.aboutBgColor)
        c.setAlpha(max(30, Theme.aboutBgAlpha // 3))
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    def paint_content(self, painter: QPainter) -> None:
        """Subtle crosshair so the node is findable but barely visible."""
        painter.save()
        r = self.rect()
        cx = r.center().x()
        cy = r.center().y()
        arm = min(r.width(), r.height()) * 0.2

        pen_color = QColor(Theme.primaryBorder)
        pen_color.setAlpha(80)
        painter.setPen(pen_color)
        painter.drawLine(int(cx - arm), int(cy), int(cx + arm), int(cy))
        painter.drawLine(int(cx), int(cy - arm), int(cx), int(cy + arm))

        # Tiny label
        painter.setOpacity(0.4)
        font = QFont(self._BODY_FONT, 7)
        painter.setFont(font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.drawText(
            QRectF(r.left(), r.bottom() - 14, r.width(), 12),
            Qt.AlignCenter,
            "null",
        )
        painter.restore()

    # NullNode has no timers, proxies, or signals of its own — no manifest
    # declarations needed, no _prepare_for_removal override.  The crew
    # handles the standard BaseNode teardown via inheritance.

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'NullNode':
        return NullNode(NullNodeData.from_dict(data))
