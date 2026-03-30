#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeNode.py ClaudeNode class
-Skeletal Claude-branded node, ready to be packed with features, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtGui import QColor

from nodes.BaseNode import BaseNode
from data.ClaudeNodeData import ClaudeNodeData
from graphics.Theme import Theme


class ClaudeNode(BaseNode):
    """
    Skeletal Claude node — a blank canvas ready for features.

    Inherits all chrome, ports, resize, hover pulse, lifecycle handling,
    and default title rendering from BaseNode.
    """
    _has_depth_toggle = True

    def __init__(self, data: ClaudeNodeData | None = None):
        if data is None:
            data = ClaudeNodeData()
        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()

    def _bg_color(self) -> QColor:
        c = QColor(Theme.claudeBgColorFront if self.data.depth_front else Theme.claudeBgColor)
        c.setAlpha(Theme.claudeBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeNode':
        return ClaudeNode(ClaudeNodeData.from_dict(data))
