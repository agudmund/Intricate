#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/TextNode.py TextNode class
-Always-editable multiline text node with Lato font, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
import random

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.TextNodeData import TextNodeData
from graphics.Theme import Theme


_BUTTON_ZONE_H = 24.0
_PAD           = 8.0


class TextNode(BaseNode):
    """
    A plain always-editable text node using Lato font.

    The QTextEdit is always visible — no double-click activation needed.
    Click anywhere on the node to start typing. Resize freely.
    """
    _has_depth_toggle = True

    def __init__(self, data: TextNodeData | None = None):
        if data is None:
            data = TextNodeData()
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
        self._editor.setFont(QFont(Theme.claudeBodyFontFamily, max(1, Theme.claudeBodyFontSize)))
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.aboutFontColor};
                font-family: {Theme.claudeBodyFontFamily};
                font-size: {Theme.claudeBodyFontSize}pt;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.focusInEvent = lambda e: (
            self._on_focused(),
            QTextEdit.focusInEvent(self._editor, e)
        )

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._position_editor()
        self._editor_proxy.show()

    def _on_text_changed(self) -> None:
        self.data.label = self._editor.toPlainText()

    def _on_focused(self) -> None:
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)

    def _position_editor(self) -> None:
        r = self.rect()
        self._editor_proxy.setGeometry(QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2,
            r.height() - _BUTTON_ZONE_H - _PAD,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        split_pix = Theme.icon(Theme.iconSplitNode, fallback_color="#9ab8d9")
        self._buttons.append(NodeButton(self, split_pix, self._split_into_about_nodes))

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT — explode body text into individual AboutNodes
    # ─────────────────────────────────────────────────────────────────────────

    def _split_into_about_nodes(self) -> None:
        """
        Split each non-empty line of the body text into its own AboutNode.

        Placement uses the same spiral-probe strategy as ClaudeNode response
        nodes: spawn off-screen, measure real size, then spiral outward from
        this node's position probing for a clear slot with PADDING breathing
        room. Each subsequent node starts its search from the previous node's
        position so the chain flows outward organically.
        """
        scene = self.scene()
        if not scene:
            return

        text = self.data.label if self._editor is None else self._editor.toPlainText()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return

        from nodes.BaseNode import BaseNode as _BaseNode

        PADDING         = 28
        PROBES_PER_RING = 16
        _OFFSCREEN      = QPointF(-999_999, -999_999)

        origin = self.pos() + QPointF(self.rect().width() + 60, 0)

        for line in lines:
            node = scene.add_about_node(pos=_OFFSCREEN, label=line)
            node.data.title = line[:40]
            nr = node.rect()
            nw, nh = nr.width(), nr.height()

            step       = max(1, int(max(nw, nh)) // 2)
            max_radius = 4000

            def _clear(p):
                candidate = QRectF(p.x() - PADDING, p.y() - PADDING,
                                   nw + PADDING * 2, nh + PADDING * 2)
                for item in scene.items(candidate):
                    if item is node:
                        continue
                    if isinstance(item, _BaseNode):
                        return False
                return True

            pos = origin
            found = _clear(origin)
            if not found:
                for radius in range(step, max_radius, step):
                    base = random.uniform(0, 2 * math.pi)
                    for k in range(PROBES_PER_RING):
                        angle = base + k * (2 * math.pi / PROBES_PER_RING)
                        candidate = QPointF(
                            origin.x() + math.cos(angle) * radius,
                            origin.y() + math.sin(angle) * radius,
                        )
                        if _clear(candidate):
                            pos = candidate
                            found = True
                            break
                    if found:
                        break

            if not found:
                pos = origin

            node.setPos(pos)
            origin = pos + QPointF(nw + 40, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        pass  # editor is always visible — nothing to paint

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_editor_proxy') and self._editor_proxy:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._editor_proxy:
            self._editor_proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self._editor_proxy and self._editor_proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                if self.scene() and self.scene().views():
                    self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
                    self.scene().views()[0].setFocus()
                event.accept()
                return
            event.accept()
            return
        super().keyPressEvent(event)

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

    def sync_data(self) -> None:
        super().sync_data()
        if self._editor:
            self.data.label = self._editor.toPlainText()

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'TextNode':
        return TextNode(TextNodeData.from_dict(data))
