#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeResponseNode.py ClaudeResponseNode class
-Multiline sticky note that captures a full Claude reply, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor, QFontMetrics, QPen

_BUTTON_ZONE_H = 24.0
_MAX_WIDTH      = 420.0
_MIN_WIDTH      = 160.0
_PAD_H          = 24.0   # horizontal padding total
_PAD_V          = 8.0    # vertical padding inside text area

from nodes.BaseNode import BaseNode
from data.ClaudeResponseNodeData import ClaudeResponseNodeData
from graphics.Theme import Theme


class ClaudeResponseNode(BaseNode):
    _has_depth_toggle = True

    def __init__(self, data: ClaudeResponseNodeData | None = None):
        if data is None:
            data = ClaudeResponseNodeData()
        if data.width == 0.0 or data.height == 0.0:
            font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
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
        _w = Theme.nodeBorderWidth
        self.normal_pen   = QPen(QColor(Theme.aboutBorderColor),         _w)
        self.hover_pen    = QPen(QColor(Theme.aboutBorderHoverColor),    _w)
        self.selected_pen = QPen(QColor(Theme.aboutBorderSelectedColor), _w)
        self.current_pen  = self.normal_pen
        self.setPen(self.current_pen)
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_editor()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_editor(self) -> None:
        self._editor = QTextEdit()
        self._editor.setFrameShape(QTextEdit.NoFrame)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.aboutFontColor};
                font-family: {Theme.aboutFontFamily};
                font-size: {Theme.aboutFontSize}pt;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.focusOutEvent = lambda e: (self._commit(), QTextEdit.focusOutEvent(self._editor, e))

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.hide()

    def _start_edit(self) -> None:
        r   = self.rect()
        pad = Theme.aboutTextPaddingLeft
        text_rect = QRectF(r.left() + pad,
                           r.top() + _BUTTON_ZONE_H + _PAD_V,
                           r.width() - pad * 2,
                           r.height() - _BUTTON_ZONE_H - _PAD_V)
        self._editor_proxy.setGeometry(text_rect)
        self._editor.setPlainText(self.data.label)
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
        self._editor_proxy.show()
        self._editor.setFocus(Qt.MouseFocusReason)

    def _commit(self) -> None:
        if not self._editor_proxy or not self._editor_proxy.isVisible():
            return
        text = self._editor.toPlainText().strip()
        if text:
            self.data.label = text
        self._editor_proxy.hide()
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self._start_edit()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self._editor_proxy and self._editor_proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._editor_proxy.hide()
                if self.scene() and self.scene().views():
                    self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
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
        if self._editor_proxy and self._editor_proxy.isVisible():
            return
        painter.save()
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        painter.setFont(font)
        painter.setPen(QColor(Theme.aboutFontColor))
        r         = self.rect()
        pad       = Theme.aboutTextPaddingLeft
        text_rect = QRectF(r.left() + pad,
                           r.top() + _BUTTON_ZONE_H + _PAD_V,
                           r.width() - pad * 2,
                           r.height() - _BUTTON_ZONE_H - _PAD_V)
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.data.label)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._editor_proxy and self._editor_proxy.isVisible():
            self._editor_proxy.hide()
            if self.scene() and self.scene().views():
                self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        self._editor = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeResponseNode':
        return ClaudeResponseNode(ClaudeResponseNodeData.from_dict(data))
