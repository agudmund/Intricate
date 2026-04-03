#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Edit
-A unified text editor widget that wraps itself in a QGraphicsProxyWidget for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPalette,
                            QTextBlockFormat, QTextCursor)
from PySide6.QtWidgets import QGraphicsProxyWidget

from widgets.PrettyMenu import StyledTextEdit
from graphics.Theme import Theme


# ── Scrollbar QSS fragment (reused by read-only / log-style editors) ─────────
_SCROLLBAR_QSS = """
    QScrollBar:vertical {{
        width: {width}px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: {handle};
        border-radius: {radius}px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
"""


class PrettyEdit(StyledTextEdit):
    """
    Themed QTextEdit that lives inside a QGraphicsProxyWidget on the canvas.

    Consolidates the inline-editor lifecycle that was duplicated across
    ImageNode, VideoNode, AboutNode, ClaudeResponseNode, TextNode, LogNode,
    and TreeNode:

        build  -> PrettyEdit(parent_node, ...)
        show   -> start_edit(text, rect)
        save   -> commit()          returns stripped text or None
        cancel -> cancel()
        die    -> teardown()        call from _prepare_for_removal

    Two modes controlled by ``always_visible``:

    *On-demand* (default) — proxy hidden at creation, shown/hidden via
    start_edit / commit / cancel.  Emits ``committed(str)`` on commit.

    *Always-visible* — proxy shown at creation, text synced via the
    ``textChanged`` signal.  ``committed`` is never emitted.
    """

    committed = Signal(str)   # on-demand mode: fired with stripped text

    def __init__(
        self,
        parent_node,                          # the QGraphicsItem that owns us
        *,
        font_family:     str  = None,         # defaults to Theme.aboutFontFamily
        font_size:       int  = None,         # defaults to Theme.aboutFontSize
        font_color:      str  = None,         # defaults to Theme.aboutFontColor
        always_visible:  bool = False,
        read_only:       bool = False,
        scrollbar:       bool = False,        # show a slim scrollbar
        scrollbar_width: int  = 4,
        placeholder:     str  = None,
        commit_on_focus_loss: bool = False,    # auto-commit when editor loses focus
    ):
        super().__init__()

        self._parent_node    = parent_node
        self._always_visible = always_visible

        # ── Resolve defaults ──────────────────────────────────────────────
        family = font_family or Theme.aboutFontFamily
        size   = font_size   or Theme.aboutFontSize
        color  = font_color  or Theme.aboutFontColor

        # ── Widget config ─────────────────────────────────────────────────
        self.setFrameShape(StyledTextEdit.NoFrame)
        self.setFont(QFont(family, max(1, size)))
        if read_only:
            self.setReadOnly(True)
        if placeholder:
            self.setPlaceholderText(placeholder)

        # ── Stylesheet ────────────────────────────────────────────────────
        qss = f"""
            QTextEdit {{
                background: transparent;
                color: {color};
                font-family: {family};
                font-size: {size}pt;
                border: none;
                padding: 0px;
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
            }}
        """
        if scrollbar:
            qss += _SCROLLBAR_QSS.format(
                width=scrollbar_width,
                handle=Theme.primaryBorder,
                radius=scrollbar_width // 2,
            )
        self.setStyleSheet(qss)

        # ── Palette-level selection colors ────────────────────────────────
        #    QPalette.setBrush accepts a QLinearGradient for Highlight,
        #    giving us the same sweep used by the context menu items.
        from PySide6.QtGui import QBrush
        grad = QLinearGradient(0, 0, 1, 0)
        grad.setCoordinateMode(QLinearGradient.ObjectMode)
        grad.setColorAt(0.0, QColor("#1e1e1e"))
        grad.setColorAt(0.4, QColor("#5c3e4f"))
        grad.setColorAt(0.7, QColor("#a56a85"))
        grad.setColorAt(1.0, QColor("#d87a9e"))
        pal = self.palette()
        pal.setBrush(QPalette.Highlight,       QBrush(grad))
        pal.setColor(QPalette.HighlightedText, QColor(Theme.aboutSelectionFontColor))
        self.setPalette(pal)

        # ── Kill internal margins so text aligns with painted drawText ────
        self.document().setDocumentMargin(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)

        # ── Override line height to tame fonts with inflated metrics ──────
        self._applyLineHeight()

        # ── Auto-commit on focus loss (on-demand editors) ─────────────────
        if commit_on_focus_loss and not always_visible:
            _original_focus_out = self.focusOutEvent

            def _focus_out_commit(event):
                self.commit()
                _original_focus_out(event)

            self.focusOutEvent = _focus_out_commit

        # ── Always-visible: lift view focus on click ──────────────────────
        if always_visible and not read_only:
            _original_focus_in = self.focusInEvent

            def _focus_in_lift(event):
                self._lift_view_focus()
                _original_focus_in(event)

            self.focusInEvent = _focus_in_lift

        # ── Proxy ─────────────────────────────────────────────────────────
        self.proxy = QGraphicsProxyWidget(parent_node)
        self.proxy.setWidget(self)

        if always_visible:
            self.proxy.show()
        else:
            self.proxy.hide()

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def position(self, rect: QRectF) -> None:
        """Move / resize the proxy to *rect* (in parent-node coordinates)."""
        self.proxy.setGeometry(rect)

    def start_edit(self, text: str = "", rect: QRectF = None,
                   select_all: bool = True) -> None:
        """
        Show the editor over *rect*, pre-filled with *text*.
        Only meaningful for on-demand editors.
        """
        if rect is not None:
            self.proxy.setGeometry(rect)
        self.setPlainText(text)
        self._applyLineHeight()
        if select_all:
            self.selectAll()
        self._lift_view_focus()
        self.proxy.show()
        self.setFocus(Qt.MouseFocusReason)

    def commit(self) -> str | None:
        """
        Hide the editor, restore view focus, emit ``committed``.
        Returns the stripped text, or ``None`` if the proxy wasn't visible.
        """
        if not self.proxy.isVisible():
            return None
        text = self.toPlainText().strip()
        self.proxy.hide()
        self._restore_view_focus()
        self.committed.emit(text)
        return text

    def cancel(self) -> None:
        """Discard edits and hide."""
        self.proxy.hide()
        self._restore_view_focus()

    def teardown(self) -> None:
        """
        Call from the owning node's ``_prepare_for_removal``.
        Hides the proxy and restores view focus if needed.
        """
        if self.proxy and self.proxy.isVisible():
            self.proxy.hide()
            self._restore_view_focus()

    # ─────────────────────────────────────────────────────────────────────────
    # LINE HEIGHT OVERRIDE
    # ─────────────────────────────────────────────────────────────────────────

    def _applyLineHeight(self) -> None:
        """Clamp line height to a fixed pixel value if configured in Theme."""
        h = Theme.aboutSelectionLineHeight
        if h <= 0:
            return
        fmt = QTextBlockFormat()
        fmt.setLineHeight(h, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeBlockFormat(fmt)
        self.setTextCursor(cursor)

    # ─────────────────────────────────────────────────────────────────────────
    # SELECTION GRADIENT
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # VIEW FOCUS MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _lift_view_focus(self) -> None:
        """Temporarily set the view to StrongFocus so this editor can receive keys."""
        node = self._parent_node
        if node.scene() and node.scene().views():
            node.scene().views()[0].setFocusPolicy(Qt.StrongFocus)

    def _restore_view_focus(self) -> None:
        """Return the view to NoFocus — editing is done."""
        node = self._parent_node
        if node.scene() and node.scene().views():
            node.scene().views()[0].setFocusPolicy(Qt.NoFocus)
