#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/CushionsNode.py CushionsNode class
-A cushioned text node with an export button, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.CushionsNodeData import CushionsNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0


class CushionsNode(BaseNode):
    """
    A cushioned text node with an export button.

    Based on the simple TextNode — always-editable multiline text area
    with an additional export action on the button toolbar.
    """
    _has_depth_toggle = True

    def __init__(self, data: CushionsNodeData | None = None):
        if data is None:
            data = CushionsNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: PrettyEdit | None = None
        self._build_editor()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(
            Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor
        )
        c.setAlpha(Theme.aboutBgAlpha)
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
            font_family=Theme.claudeBodyFontFamily,
            font_size=Theme.claudeBodyFontSize,
            font_color=Theme.nodeFontColor,
            always_visible=True,
        )
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._position_editor()

    def _on_text_changed(self) -> None:
        self.data.label = self._editor.toPlainText()

    def _position_editor(self) -> None:
        r = self.rect()
        self._editor.position(QRectF(
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
        export_pix = Theme.icon(Theme.iconExport, fallback_color="#a8c0a8")
        self._buttons.append(NodeButton(self, export_pix, self._export))

    def _export(self) -> None:
        """Split paragraphs into chained WarmNodes with organic scatter.

        Each paragraph becomes its own WarmNode, wired in sequence.
        Placement wanders from the previous node (Gaussian cluster with
        occasional fling) then uses spiral_place for collision avoidance —
        same algorithm as the Info/MarkdownNode scatter.
        """
        import re
        from PySide6.QtCore import QPointF, QRectF

        scene = self.scene()
        if not scene:
            return

        text = self.data.label if self._editor is None else self._editor.toPlainText()
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        if not paragraphs:
            return

        from graphics.Connection import Connection
        from utils.placement import spiral_place

        PADDING    = 28
        _OFFSCREEN = QPointF(-999_999, -999_999)

        prev_node = self

        for paragraph in paragraphs:
            from nodes.WarmNode import WarmNode
            from data.WarmNodeData import WarmNodeData

            wdata = WarmNodeData(body_text=paragraph, title="")
            node = WarmNode(wdata)
            node.setPos(_OFFSCREEN)
            scene.addItem(node)
            scene.raise_node(node)

            # Let the editor lay out, then resize to fit all text.
            if node._editor:
                doc = node._editor.document()
                doc.setTextWidth(node.rect().width() - PADDING * 2)
                doc_h = doc.size().height()
                needed = 90.0 + doc_h + PADDING
                if needed > node.rect().height():
                    r = node.rect()
                    node.setRect(QRectF(r.x(), r.y(), r.width(), needed))
                    node.data.height = needed

            chain_origin = self._wander_origin(prev_node)
            pos = spiral_place(
                scene, node, origin=chain_origin,
                fallback=chain_origin, padding=PADDING,
            )
            node.setPos(pos)

            conn = Connection(prev_node, node)
            scene.addItem(conn)
            prev_node = node

    @staticmethod
    def _wander_origin(prev_node) -> 'QPointF':
        """Pick a random origin near *prev_node* — organic desk-scatter."""
        import math
        import random
        from PySide6.QtCore import QPointF

        pr = prev_node.rect()
        cx = prev_node.pos().x() + pr.width()  / 2
        cy = prev_node.pos().y() + pr.height() / 2

        angle = random.uniform(0, 2 * math.pi)

        if random.random() < 0.15:
            distance = random.uniform(500, 900)
        else:
            distance = random.gauss(260, 80)
            distance = max(120, distance)

        return QPointF(
            cx + math.cos(angle) * distance,
            cy + math.sin(angle) * distance,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        pass  # editor is always visible — nothing to paint

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_editor') and self._editor:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._editor:
            self._editor.proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self._editor and self._editor.proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._editor._restore_view_focus()
                if self.scene() and self.scene().views():
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
        if self._editor:
            self._editor.teardown()
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
    def from_dict(data: dict) -> 'CushionsNode':
        return CushionsNode(CushionsNodeData.from_dict(data))
