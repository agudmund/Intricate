#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AboutNode.py AboutNode class
-A minimal sticky-note node. A category memo planted near groups of nodes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget
from widgets.PrettyMenu import StyledLineEdit as QLineEdit
from PySide6.QtCore import Qt, QRectF, QSizeF
from PySide6.QtGui import QPainter, QFont, QColor, QFontMetrics, QPen

_BUTTON_ZONE_H = 40.0   # px reserved for button strip (4 pad + 32 button + 4 gap)
_Z_FRONT       = 10.0
_Z_BACK        = -10.0

from nodes.BaseNode import BaseNode
from data.AboutNodeData import AboutNodeData
from graphics.Theme import Theme


class AboutNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = False
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
        if data.height == 0.0:
            data.height = Theme.aboutMinHeight / 2 + 5
        if data.width == 0.0:
            font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
            text_w = QFontMetrics(font).horizontalAdvance(data.label or data.title)
            data.width = text_w + 28   # snug right edge

        super().__init__(data)

        self.setBrush(self._bg_color())
        _w = Theme.nodeBorderWidth
        self.normal_pen   = QPen(QColor(Theme.aboutBorderColor),         _w)
        self.hover_pen    = QPen(QColor(Theme.aboutBorderHoverColor),    _w)
        self.selected_pen = QPen(QColor(Theme.aboutBorderSelectedColor), _w)
        self.current_pen  = self.normal_pen
        self.setPen(self.current_pen)
        self._min_height = Theme.aboutMinHeight / 2 + 5
        self._apply_depth()

        self._editor: QLineEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_editor()

        # Button row starts hidden — double-click the top strip to reveal
        self._buttons_visible = False
        for btn in self._buttons:
            btn.hide()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────


    def _bg_color(self) -> QColor:
        acc = getattr(self.data, 'node_tint', '')
        if acc:
            c = QColor(acc)
            if not c.isValid():
                c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        else:
            c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        # Stop any in-flight animation before setting the new color — otherwise
        # _on_bg_changed fires after us and overwrites the brush with the old target.
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _top_offset(self) -> float:
        """Vertical space reserved above the text — full button zone or minimal pad."""
        return _BUTTON_ZONE_H if self._buttons_visible else 6.0

    def _build_editor(self) -> None:
        self._editor = QLineEdit()
        self._editor.setAlignment(Qt.AlignLeft)
        self._editor.setFrame(False)
        self._editor.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {Theme.aboutFontColor};
                font-family: {Theme.aboutFontFamily};
                font-size: {Theme.aboutFontSize}pt;
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
        r = self.rect()
        pad = Theme.aboutTextPaddingLeft
        top = self._top_offset()
        text_rect = QRectF(r.left() + pad, r.top() + top + Theme.aboutEditorVerticalOffset + Theme.aboutTextPaddingTop, r.width() - pad, r.height() - top)
        self._editor_proxy.setGeometry(text_rect)
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
        # Top strip above the text area — toggle button row
        if event.pos().y() < self.rect().top() + _BUTTON_ZONE_H:
            self._buttons_visible = not self._buttons_visible
            for btn in self._buttons:
                btn.setVisible(self._buttons_visible)
            event.accept()
            return
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
        r = self.rect()
        pad = Theme.aboutTextPaddingLeft
        top = self._top_offset()
        text_rect = QRectF(r.left() + pad, r.top() + top + Theme.aboutFontVerticalOffset + Theme.aboutTextPaddingTop, r.width() - pad, r.height() - top)
        label = self.data.label or self.data.title
        label = QFontMetrics(font).elidedText(label, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, label)
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
