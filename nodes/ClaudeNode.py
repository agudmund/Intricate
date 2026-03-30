#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeNode.py ClaudeNode class
-Skeletal Claude-branded node, ready to be packed with features, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.ClaudeNodeData import ClaudeNodeData
from graphics.Theme import Theme

_BUTTON_ZONE_H = 28.0   # px reserved for the button strip at the top


class ClaudeNode(BaseNode):
    """
    Skeletal Claude node — a blank canvas ready for features.

    Inherits all chrome, ports, resize, hover pulse, and lifecycle handling
    from BaseNode. Type-specific visuals live in paint_content(); everything
    else is intentionally minimal until features are added.
    """

    def __init__(self, data: ClaudeNodeData | None = None):
        if data is None:
            data = ClaudeNodeData()
        super().__init__(data)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r = self.rect()
        content_rect = QRectF(
            r.left()  + 12,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - 24,
            r.height()- _BUTTON_ZONE_H - 8,
        )
        painter.setPen(QColor(Theme.textPrimary))
        font = QFont(Theme.aboutFontFamily, Theme.aboutFontSize)
        painter.setFont(font)
        painter.drawText(content_rect, Qt.AlignHCenter | Qt.AlignVCenter, self.data.title)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeNode':
        return ClaudeNode(ClaudeNodeData.from_dict(data))
