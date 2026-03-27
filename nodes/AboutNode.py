#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/AboutNode.py
-A minimal sticky-note node. A category memo planted near groups of nodes.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget, QLineEdit
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.AboutNodeData import AboutNodeData
from graphics.Theme import Theme


class AboutNode(BaseNode):
    """
    A minimal sticky-note node.

    Smaller than a WarmNode, no body area — just a single editable label
    painted centered in the node. Double-click anywhere to edit the label.
    Used as a category memo planted near groups of nodes, detached.

    The label editor uses the same focus-lift pattern as ImageNode caption —
    briefly lifts the view's NoFocus policy during editing, restores on commit.
    """

    def __init__(self, data: AboutNodeData | None = None):
        if data is None:
            data = AboutNodeData()
        super().__init__(data)

        self._editor: QLineEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_editor(self) -> None:
        self._editor = QLineEdit()
        self._editor.setAlignment(Qt.AlignCenter)
        self._editor.setFrame(False)
        self._editor.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 10pt;
                font-weight: bold;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.returnPressed.connect(self._commit)
        self._editor.editingFinished.connect(self._commit)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.hide()

    def _start_edit(self) -> None:
        self._editor_proxy.setGeometry(self.rect())
        self._editor.setText(self.data.label or self.data.title)
        self._editor.selectAll()
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
        self._editor_proxy.show()
        self._editor.setFocus(Qt.MouseFocusReason)

    def _commit(self) -> None:
        if not self._editor_proxy.isVisible():
            return
        text = self._editor.text().strip()
        if text:
            self.data.label = text
            self.data.title = text
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
        font = QFont(Theme.healthFontFamily, 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(Theme.textPrimary))
        painter.drawText(self.rect(), Qt.AlignCenter,
                         self.data.label or self.data.title)
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
    def from_dict(data: dict) -> 'AboutNode':
        return AboutNode(AboutNodeData.from_dict(data))
