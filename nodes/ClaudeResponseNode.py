#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeResponseNode.py ClaudeResponseNode class
-Multiline sticky note that captures a full Claude reply, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor, QFontMetrics

from utils.pickers.IconPicker import emojiIcons

_BUTTON_ZONE_H = 40.0
_MAX_WIDTH      = 420.0
_MIN_WIDTH      = 160.0
_PAD_H          = 24.0   # horizontal padding total
_PAD_V          = 8.0    # vertical padding inside text area

from nodes.BaseNode import BaseNode
from data.ClaudeResponseNodeData import ClaudeResponseNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


class ClaudeResponseNode(BaseNode):
    _has_depth_toggle = True

    def __init__(self, data: ClaudeResponseNodeData | None = None):
        if data is None:
            data = ClaudeResponseNodeData()
        if data.width == 0.0 or data.height == 0.0:
            font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
            font.setStyleName("MediumOblique")
            fm   = QFontMetrics(font)
            wrap_width = max(_MIN_WIDTH, min(_MAX_WIDTH, fm.horizontalAdvance(data.label) + _PAD_H))
            text_w     = int(wrap_width - _PAD_H)
            bound      = fm.boundingRect(0, 0, text_w, 0,
                                         Qt.TextWordWrap | Qt.AlignLeft,
                                         data.label)
            if data.width == 0.0:
                data.width  = wrap_width
            if data.height == 0.0:
                data.height = bound.height() + _BUTTON_ZONE_H + _PAD_V * 2 + Theme.aboutMinHeight

        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: PrettyEdit | None = None
        self._build_editor()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        acc = getattr(self.data, 'node_tint', '')
        if acc:
            c = QColor(acc)
            if not c.isValid():
                c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        else:
            c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        c.setAlpha(Theme.claudeResponseTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_editor(self) -> None:
        self._editor = PrettyEdit(
            self,
            font_family=Theme.aboutFontFamily,
            font_size=Theme.aboutFontSize,
            font_color=Theme.nodeFontColor,
            commit_on_focus_loss=True,
        )
        self._editor.committed.connect(self._on_committed)

    def _edit_rect(self) -> QRectF:
        r   = self.rect()
        pad = Theme.aboutTextPaddingLeft
        content_top = r.top() + self._anim_top_offset + _PAD_V
        return QRectF(r.left() + pad,
                      content_top,
                      r.width() - pad * 2,
                      r.height() - (content_top - r.top()) - _PAD_V)

    def _start_edit(self) -> None:
        self._editor.start_edit(self.data.label, self._edit_rect(), select_all=False)

    def _on_committed(self, text: str) -> None:
        if text:
            self.data.label = text
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self._start_edit()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self._editor and self._editor.proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._editor.cancel()
                self.update()
                event.accept()
                return
            event.accept()
            return
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        if self._editor and self._editor.proxy.isVisible():
            return
        painter.save()

        # ── Label text — below button strip ──────────────────────────────────
        r   = self.rect()
        pad = Theme.aboutTextPaddingLeft
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        painter.setFont(font)
        painter.setPen(QColor(Theme.nodeFontColor))
        content_top = r.top() + self._anim_top_offset + _PAD_V
        text_rect = QRectF(r.left() + pad,
                           content_top,
                           r.width() - pad * 2,
                           r.height() - (content_top - r.top()) - _PAD_V)
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.data.label)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _demolition_pre(self) -> None:
        if self._editor:
            self._editor.teardown()
        self._editor = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeResponseNode':
        return ClaudeResponseNode(ClaudeResponseNodeData.from_dict(data))
