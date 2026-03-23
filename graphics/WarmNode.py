#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/WarmNode.py
-The main content node. Free-form text with an emoji accent and editable title.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from .BaseNode import BaseNode
from .WarmNodeData import WarmNodeData
from .Theme import Theme


# Layout constants
EMOJI_SIZE      = 28.0      # Emoji accent area at top-left
TITLE_HEIGHT    = 22.0      # Title band below emoji row
PADDING         = 10.0      # General internal padding
BODY_TOP        = PADDING + EMOJI_SIZE + 4.0    # Body text starts here


class WarmNode(BaseNode):
    """
    The main content node — the star of the show.

    Layout (top to bottom):
        ── emoji + title row ──
        ── body text area (QTextEdit proxy, editable) ──

    Double-click anywhere in the body area activates the text editor.
    The title is painted directly and edited via double-click on the title zone.
    The emoji is painted as an accent — changeable via future emoji picker.

    Serialization:
        body_text and emoji are stored in WarmNodeData.
        Both survive session save/load cleanly.
    """

    def __init__(self, data: WarmNodeData | None = None):
        if data is None:
            data = WarmNodeData()
        super().__init__(data)

        # ── Body text editor ──────────────────────────────────────────────────
        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_body_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT ZONES
    # ─────────────────────────────────────────────────────────────────────────

    def _emoji_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(r.x() + PADDING, r.y() + PADDING, EMOJI_SIZE, EMOJI_SIZE)

    def _title_rect(self) -> QRectF:
        r  = self.rect()
        er = self._emoji_rect()
        return QRectF(
            er.right() + 6.0,
            r.y() + PADDING,
            r.width() - er.right() - PADDING - 6.0,
            EMOJI_SIZE
        )

    def _body_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + PADDING,
            r.y() + BODY_TOP,
            r.width()  - PADDING * 2,
            r.height() - BODY_TOP - PADDING,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BODY EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_body_editor(self) -> None:
        """Build the QTextEdit proxy, hidden until double-clicked."""
        self._editor = QTextEdit()
        self._editor.setFrameStyle(0)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.setPlainText(self.data.body_text)
        self._editor.textChanged.connect(self._on_text_changed)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.setGeometry(self._body_rect())
        self._editor_proxy.show()   # WarmNode shows editor by default — it IS the content

    def _on_text_changed(self) -> None:
        """Sync text to data on every keystroke — no explicit commit needed."""
        if self._editor:
            self.data.body_text = self._editor.toPlainText()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        """Focus the body editor on double-click anywhere in the body zone."""
        if self._body_rect().contains(event.pos()):
            if self.scene() and self.scene().views():
                self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
            self._editor_proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        """Restore view focus policy when the node loses focus."""
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        super().focusOutEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()

        # ── Emoji accent ──────────────────────────────────────────────────────
        emoji_font = QFont(Theme.healthFontFamily, 16)
        painter.setFont(emoji_font)
        painter.setPen(QColor(Theme.textPrimary))
        painter.drawText(self._emoji_rect(), Qt.AlignCenter, self.data.emoji)

        # ── Title ─────────────────────────────────────────────────────────────
        title_font = QFont(Theme.healthFontFamily, 9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(Theme.textPrimary))
        painter.drawText(self._title_rect(), Qt.AlignVCenter | Qt.AlignLeft,
                         self.data.title)

        # ── Divider under header ──────────────────────────────────────────────
        r   = self.rect()
        div_y = r.y() + PADDING + EMOJI_SIZE + 2.0
        painter.setPen(QPen(QColor(Theme.primaryBorder), 1.0, Qt.DotLine))
        painter.drawLine(
            QPointF(r.x() + PADDING, div_y),
            QPointF(r.right() - PADDING, div_y)
        )

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if self._editor_proxy:
            self._editor_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._editor_proxy:
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
    def from_dict(data: dict) -> 'WarmNode':
        return WarmNode(WarmNodeData.from_dict(data))
