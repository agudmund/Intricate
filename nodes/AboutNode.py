#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AboutNode.py AboutNode class
-A minimal sticky-note node. A category memo planted near groups of nodes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF, QSizeF
from PySide6.QtGui import QPainter, QFont, QColor, QFontMetrics

_Z_FRONT       = 10.0
_Z_BACK        = -10.0

from nodes.BaseNode import BaseNode
from data.AboutNodeData import AboutNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


class AboutNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = False
    # Tighter than the general node default (8.0).  AboutNodes are sticky-note
    # labels — the top strip is purely visual now that button reveal has moved
    # to the resize gesture.  Matched visually against the bottom padding.
    _HIDDEN_TOP_OFFSET = 2.0
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

        # Default spawn dimensions match the tight layout _auto_expand
        # produces once the node has content — top offset + single-line
        # metrics + bottom padding.  No more manual yank-to-tighten on every
        # fresh AboutNode; defaults spawn in their correct proportions.
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        font.setStyleName(self._TITLE_STYLE)
        fm = QFontMetrics(font)
        if data.height == 0.0:
            data.height = AboutNode._HIDDEN_TOP_OFFSET + fm.lineSpacing() + 2
        if data.width == 0.0:
            data.width = fm.horizontalAdvance(data.label or data.title) + 28   # snug right edge

        super().__init__(data)

        # Start with shelf collapsed — AboutNode shows buttons only on demand
        # (revealed by dragging the resize handle; hidden by clicking the shelf
        # background once revealed).  See Documents/Texture Notes.md for the
        # full story behind this bespoke interaction model.
        self._buttons_visible = False
        self._anim_top_offset = self._HIDDEN_TOP_OFFSET
        for btn in self._buttons:
            btn.hide()

        self.setBrush(self._bg_color())
        # Boundless — AboutNodes double as colour-indent stickers without text,
        # so they're allowed to shrink freely below the text-holding breathing floor.
        self._min_height = 0
        self._apply_depth()

        self._editor: PrettyEdit | None = None

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
        from utils.pickers.IconPicker import emojiIcons
        self._shuffle_emoji = random.choice(emojiIcons)
        self._shuffle_btn.update()

    # Legacy hardcoded tints that mean "use Theme default" — not a real custom tint
    _LEGACY_TINTS = {"#2a3a2f", "#322a3a"}

    def _bg_color(self) -> QColor:
        acc = getattr(self.data, 'node_tint', '')
        if acc and acc.lower() not in self._LEGACY_TINTS:
            c = QColor(acc)
            if not c.isValid():
                c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        else:
            c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        c.setAlpha(Theme.aboutTransparency)
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

    def _build_editor(self) -> None:
        self._editor = PrettyEdit(
            self,
            font_family=Theme.aboutFontFamily,
            font_size=Theme.aboutFontSize,
            font_color=Theme.nodeFontColor,
            commit_on_focus_loss=True,
            enter_commits=True,
        )
        self._editor.committed.connect(self._on_committed)
        self._editor.document().contentsChanged.connect(self._auto_expand)

    def _edit_rect(self) -> QRectF:
        r = self.rect()
        padL = Theme.aboutTextPaddingLeft
        padR = Theme.aboutTextPaddingRight
        top = self._anim_top_offset
        return QRectF(r.left() + padL, r.top() + top + Theme.nodeTextPaddingTop, r.width() - padL - padR, r.height() - top)

    def _auto_expand(self) -> None:
        """Grow (or shrink) the node live while the user types."""
        if self._editor is None or not self._editor.proxy.isVisible():
            return
        doc  = self._editor.document()
        padL = Theme.aboutTextPaddingLeft
        padR = Theme.aboutTextPaddingRight
        padT = Theme.nodeTextPaddingTop
        top  = self._anim_top_offset

        # Let the document measure its natural (unwrapped) width so the node
        # stretches horizontally as the user types rather than wrapping down.
        doc.setTextWidth(-1)
        doc_w = doc.idealWidth()
        doc_h = doc.size().height()

        new_w = max(self._min_width,  doc_w + padL + padR + 8)
        new_h = max(self._min_height, doc_h + top  + padT + 2)

        cur = self.rect()
        if abs(new_w - cur.width()) < 1 and abs(new_h - cur.height()) < 1:
            return  # nothing meaningful changed

        self.prepareGeometryChange()
        self.setRect(QRectF(cur.topLeft(), QSizeF(new_w, new_h)))
        self._editor.position(self._edit_rect())
        self.update()

    def _start_edit(self) -> None:
        if self._editor is None:
            self._build_editor()
        # Flush the device-coordinate cache so the old painted title doesn't
        # bleed through behind the editor overlay.
        from PySide6.QtWidgets import QGraphicsItem
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._editor.start_edit(self.data.label or self.data.title, self._edit_rect())

    def _on_committed(self, text: str) -> None:
        self.data.label = text
        self.data.title = text
        # Invalidate the DeviceCoordinateCache — without this, Qt reuses
        # the stale cached pixmap that still contains the old text.
        from PySide6.QtWidgets import QGraphicsItem
        self.prepareGeometryChange()
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    # Px of vertical change during a resize before the shelf toggles.
    # Small threshold = deliberate-direction detection; prevents twitchy
    # flips from sub-pixel tremor on the drag.
    _RESIZE_SHELF_THRESHOLD = 5.0

    def mouseMoveEvent(self, event) -> None:
        # Defer to BaseNode first so the resize actually happens and
        # self.rect() reflects the updated geometry before we inspect it.
        super().mouseMoveEvent(event)
        # ── Bidirectional shelf coupling ─────────────────────────────────
        # Resize direction drives shelf state:
        #   • growing taller past the threshold  → reveal (with new emoji)
        #   • shrinking shorter past the threshold → hide
        # "I want to see the tools" is grow-intent; "I want to fit tight"
        # is shrink-intent.  Width-only tuning is silent — shelf state
        # only reacts to height delta.
        if not self._is_resizing:
            return
        delta_h = self.rect().height() - self._resize_start_rect.height()
        if not self._buttons_visible and delta_h > self._RESIZE_SHELF_THRESHOLD:
            self._reshuffle_emoji()
            self._toggle_shelf()
        elif self._buttons_visible and delta_h < -self._RESIZE_SHELF_THRESHOLD:
            self._toggle_shelf()

    def mouseDoubleClickEvent(self, event) -> None:
        # Don't enter edit mode if the double-click landed in the visible
        # shelf zone — the user is interacting with buttons, not requesting
        # text edit.  When the shelf is hidden the top strip is purely
        # visual, so double-click there falls through to edit like the body.
        if self._buttons_visible and event.pos().y() < self._BUTTON_ZONE_H:
            event.accept()
            return
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
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        font.setStyleName(self._TITLE_STYLE)
        painter.setFont(font)
        painter.setPen(QColor(Theme.aboutTextColor))
        r = self.rect()
        padL = Theme.aboutTextPaddingLeft
        padR = Theme.aboutTextPaddingRight
        top = self._anim_top_offset
        text_rect = QRectF(r.left() + padL, r.top() + top + Theme.nodeTextPaddingTop, r.width() - padL - padR, r.height() - top)
        label = self.data.label or self.data.title

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

    def _demolition_pre(self) -> None:
        # Editor owns a QTextDocument whose contentsChanged signal we
        # wired into _auto_expand — sever it before teardown or a late
        # edit event will hit a dead slot.  teardown() handles the
        # proxy-widget cleanup inside PrettyEdit itself.
        if self._editor:
            try:
                self._editor.document().contentsChanged.disconnect(self._auto_expand)
            except (RuntimeError, TypeError):
                pass
            self._editor.teardown()
        self._editor = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'AboutNode':
        return AboutNode(AboutNodeData.from_dict(data))
