#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/CushionsNode.py CushionsNode class
-A cushioned text node with an export button, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QFontMetrics, QColor

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

    # Class-level shared font cache for idle-paint text.  Same pattern
    # AboutNode / TextNode / WarmNode use: one QFont + one QFontMetrics
    # across every CushionsNode instance.
    _SHARED_FONTS: dict = {}

    def __init__(self, data: CushionsNodeData | None = None):
        if data is None:
            data = CushionsNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        # Lazy editor — paint_content renders the label text in the
        # idle state; the PrettyEdit only builds on first double-click.
        # Matches the TextNode conversion (commit a2337bb).
        self._editor: PrettyEdit | None = None

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(
            Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor
        )
        c.setAlpha(Theme.aboutTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_editor(self) -> None:
        """Lazy-build the PrettyEdit on first double-click.  Idempotent."""
        if self._editor is not None:
            return
        self._editor = PrettyEdit(
            self,
            font_family=Theme.claudeBodyFontFamily,
            font_size=Theme.claudeBodyFontSize,
            font_color=Theme.nodeFontColor,
            always_visible=False,
            commit_on_focus_loss=True,
        )
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.committed.connect(self._on_committed)
        self._position_editor()

    def _on_text_changed(self) -> None:
        if self._editor is not None:
            self.data.label = self._editor.toPlainText()

    def _on_committed(self, text: str) -> None:
        """Editor lost focus — PrettyEdit has hidden its proxy;
        paint_content takes over the visual."""
        self.data.label = text
        self.update()

    def _body_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2,
            r.height() - _BUTTON_ZONE_H - _PAD,
        )

    def _position_editor(self) -> None:
        if self._editor is not None:
            self._editor.position(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        export_pix = Theme.icon(Theme.iconExport, fallback_color="#a8c0a8")
        self._buttons.append(NodeButton(self, export_pix, self._export))

    def _export(self) -> None:
        """Split into chained WarmNodes with organic scatter.

        Paragraphs are the preferred breakpoint, but content without paragraph
        breaks cascades through finer boundaries (lines → sentences → words)
        via ``utils.text_chunker.chunk_text`` — so a single-paragraph multi-
        megabyte blob splits into many manageable nodes instead of one
        skyscraper that crashes Qt on render (the 2026-04-18 lesson).
        Placement is delegated to ``utils.placement.chain_spawn`` — the
        canonical organic-scatter helper, shared with WarmNode's paste-
        split and any future spawn path.  CushionsNode is the originating
        node of the whole split-into-chained-WarmNodes pattern; the
        helper is its descendants' shared inheritance.
        """
        from utils.text_chunker import paragraph_chunks
        from utils.placement import chain_spawn
        from nodes.WarmNode import WARM_SPLIT_SAFETY_CEILING, WarmNode
        from data.WarmNodeData import WarmNodeData

        scene = self.scene()
        if not scene:
            return

        text = self.data.label if self._editor is None else self._editor.toPlainText()
        if not text or not text.strip():
            return
        paragraphs = paragraph_chunks(text, WARM_SPLIT_SAFETY_CEILING)
        if not paragraphs:
            return

        def _warm_factory(paragraph: str) -> 'WarmNode':
            # No ``title=`` override — WarmNodeData's default factory fires
            # PhrasePicker.randomling so each spawned node gets its own
            # placeholder title.
            return WarmNode(WarmNodeData(body_text=paragraph))

        chain_spawn(scene, source_node=self, items=paragraphs, factory=_warm_factory)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        # Editor overlaid (active edit): the editor paints itself, skip.
        if (self._editor is not None
                and getattr(self._editor, 'proxy', None) is not None
                and self._editor.proxy.isVisible()):
            return
        label = self.data.label or ""
        if not label:
            return

        fkey = (Theme.claudeBodyFontFamily, Theme.claudeBodyFontSize)
        cached = CushionsNode._SHARED_FONTS.get(fkey)
        if cached is None:
            f = QFont(Theme.claudeBodyFontFamily, max(1, Theme.claudeBodyFontSize))
            cached = (f, QFontMetrics(f))
            CushionsNode._SHARED_FONTS[fkey] = cached
        font, _ = cached

        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.drawText(
            self._body_rect(),
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            label,
        )
        painter.restore()

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_editor') and self._editor:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self._ensure_editor()
        self._editor.start_edit(self.data.label, self._body_rect(), select_all=False)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if (self._editor is not None
                and getattr(self._editor, 'proxy', None) is not None
                and self._editor.proxy.isVisible()):
            if event.key() == Qt.Key_Escape:
                self._editor.commit()
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

    def _demolition_pre(self) -> None:
        if self._editor:
            self._editor.teardown()
        self._editor = None

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
