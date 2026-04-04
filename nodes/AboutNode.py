#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AboutNode.py AboutNode class
-A minimal sticky-note node. A category memo planted near groups of nodes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF, QSizeF, QEasingCurve, QVariantAnimation
from PySide6.QtGui import (QPainter, QFont, QColor, QFontMetrics,
                           QTextDocument, QTextCursor, QTextBlockFormat)

_BUTTON_ZONE_H = 40.0   # px reserved for button strip (4 pad + 32 button + 4 gap)
_Z_FRONT       = 10.0
_Z_BACK        = -10.0

from nodes.BaseNode import BaseNode
from data.AboutNodeData import AboutNodeData
from graphics.Theme import Theme
from widgets.PrettyEdit import PrettyEdit


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
            data.height = Theme.aboutMinHeight + 2
        if data.width == 0.0:
            font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
            text_w = QFontMetrics(font).horizontalAdvance(data.label or data.title)
            data.width = text_w + 28   # snug right edge

        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height = Theme.aboutMinHeight / 2 + 5
        self._apply_depth()

        self._editor: PrettyEdit | None = None
        self._build_editor()

        # Button row starts hidden — double-click the top strip to reveal
        self._buttons_visible = False
        self._anim_top_offset = 8.0
        self._shelf_anim = QVariantAnimation()
        self._shelf_anim.setDuration(250)
        self._shelf_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._shelf_anim.valueChanged.connect(self._on_shelf_tick)
        self._shelf_anim.finished.connect(self._on_shelf_done)
        for btn in self._buttons:
            btn.hide()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import EmojiButton
        self._shuffle_emoji = ""
        self._shuffle_btn = EmojiButton(
            self,
            get_emoji=lambda: self._shuffle_emoji,
            set_emoji=lambda e: setattr(self, '_shuffle_emoji', e),
        )
        self._buttons.append(self._shuffle_btn)
        super()._build_buttons()

    def _reshuffle_emoji(self) -> None:
        import random
        from utils.IconPicker import emojiIcons
        self._shuffle_emoji = random.choice(emojiIcons)
        self._shuffle_btn.update()

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
        """Vertical space reserved above the text — animated between 8px and button zone."""
        return self._anim_top_offset

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
        r = self.rect()
        padL = Theme.aboutTextPaddingLeft
        padR = Theme.aboutTextPaddingRight
        top = self._top_offset()
        return QRectF(r.left() + padL, r.top() + top + Theme.aboutFontVerticalOffset + Theme.aboutTextPaddingTop, r.width() - padL - padR, r.height() - top)

    def _start_edit(self) -> None:
        self._editor.start_edit(self.data.label or self.data.title, self._edit_rect())

    def _on_committed(self, text: str) -> None:
        self.data.label = text
        self.data.title = text
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        # Top strip above the text area — toggle button row
        # Use actual top offset so the hit area never overlaps the text
        if event.pos().y() < self.rect().top() + self._top_offset():
            self._buttons_visible = not self._buttons_visible
            self._shelf_anim.stop()
            if self._buttons_visible:
                # Opening — animate offset up, show buttons at the end
                self._shelf_anim.setStartValue(self._anim_top_offset)
                self._shelf_anim.setEndValue(_BUTTON_ZONE_H)
                self._reshuffle_emoji()
            else:
                # Closing — hide buttons immediately, animate offset down
                for btn in self._buttons:
                    btn.hide()
                self._shelf_anim.setStartValue(self._anim_top_offset)
                self._shelf_anim.setEndValue(8.0)
            self._shelf_anim.start()
            event.accept()
            return
        self._start_edit()
        event.accept()

    def _on_shelf_tick(self, value: float) -> None:
        self._anim_top_offset = value
        self.update()

    def _on_shelf_done(self) -> None:
        if self._buttons_visible:
            self._position_buttons()
            for btn in self._buttons:
                btn.show()

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
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        painter.setFont(font)
        painter.setPen(QColor(Theme.nodeFontColor))
        r = self.rect()
        padL = Theme.aboutTextPaddingLeft
        padR = Theme.aboutTextPaddingRight
        top = self._top_offset()
        text_rect = QRectF(r.left() + padL, r.top() + top + Theme.aboutFontVerticalOffset + Theme.aboutTextPaddingTop, r.width() - padL - padR, r.height() - top)
        label = self.data.label or self.data.title

        spacing = Theme.aboutLineSpacing
        if spacing:
            # Use QTextDocument to render with custom line spacing.
            # Must match PrettyEdit exactly: LineDistanceHeight mode and
            # the same pad_top that the editor stylesheet applies when
            # spacing is negative — otherwise painted text and editor
            # text land on different pixels.
            pad_top = max(0, int(abs(spacing))) if spacing < 0 else 0
            doc = QTextDocument()
            doc.setDefaultFont(font)
            doc.setTextWidth(text_rect.width())
            doc.setDocumentMargin(0)
            doc.setPlainText(label)
            fmt = QTextBlockFormat()
            fmt.setLineHeight(spacing, QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value)
            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.Document)
            cursor.mergeBlockFormat(fmt)
            painter.translate(text_rect.left(), text_rect.top() + pad_top)
            doc.drawContents(painter, QRectF(0, 0, text_rect.width(), text_rect.height()))
        else:
            # Fast path — default font spacing
            fm = QFontMetrics(font)
            bounding = fm.boundingRect(text_rect.toRect(), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, label)
            if bounding.height() > text_rect.height() or bounding.width() > text_rect.width():
                lines = label.splitlines(keepends=True)
                visible = ""
                line_h = fm.lineSpacing()
                max_lines = max(1, int(text_rect.height() / line_h)) if line_h > 0 else 1
                for i, ln in enumerate(lines):
                    if i >= max_lines:
                        break
                    visible += ln
                visible = visible.rstrip()
                if len(visible) < len(label.rstrip()):
                    visible = visible + "…"
                label = visible
            painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, label)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._shelf_anim.stop()
        if self._editor:
            self._editor.teardown()
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
