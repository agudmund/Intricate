#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/FbxNode.py FbxNode class
-A future home for FBX 3D model visualization on the canvas for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.FbxNodeData import FbxNodeData
from pretty_widgets.graphics.Theme import Theme


class FbxNode(BaseNode):
    """
    Placeholder node for FBX 3D model viewing.

    Will eventually load vertices from fluffandhoney.dll,
    render point clouds with perspective projection,
    and let you orbit the camera with a scrubber.

    For now it just sits on the canvas looking pretty,
    waiting for a morning coffee and a curious mind.
    """

    _has_depth_toggle = True

    def __init__(self, data: FbxNodeData | None = None):
        if data is None:
            data = FbxNodeData()
        super().__init__(data)

        c = QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        self.setBrush(c)
        self._apply_depth()

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)
        r = self.rect()

        # ── FBX label — centred, large ────────────────────────────────────
        label_font = QFont(Theme.healthFontFamily, 18)
        painter.setFont(label_font)
        painter.setPen(QColor(Theme.textPrimary))

        body_top = self._content_top() + self._BODY_OFFSET
        body_rect = QRectF(
            r.x() + 10, body_top,
            r.width() - 20, r.height() - body_top - 10,
        )

        # Show filename stem if a path is set, otherwise just "FBX"
        if self.data.fbx_path:
            stem = Path(self.data.fbx_path).stem
            text = stem
        else:
            text = "FBX"

        painter.drawText(body_rect, Qt.AlignCenter, text)

    # ─────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'FbxNode':
        return FbxNode(FbxNodeData.from_dict(data))
