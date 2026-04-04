#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Edit
-A unified text editor widget that wraps itself in a QGraphicsProxyWidget for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                            QPainterPath, QPalette, QTextBlockFormat,
                            QTextCharFormat, QTextCursor, QTextLayout)
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
        font_color:      str  = None,         # defaults to Theme.nodeFontColor
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
        color  = font_color  or Theme.nodeFontColor

        # ── Widget config ─────────────────────────────────────────────────
        self.setFrameShape(StyledTextEdit.NoFrame)
        self.setFont(QFont(family, max(1, size)))
        if read_only:
            self.setReadOnly(True)
        if placeholder:
            self.setPlaceholderText(placeholder)

        # ── Stylesheet ────────────────────────────────────────────────────
        # When line_spacing is negative the text gets pulled upward and
        # can sit flush against the top border.  Compensate with a gentle
        # top padding derived from the magnitude of that spacing.
        spacing = Theme.aboutLineSpacing
        pad_top = max(0, int(abs(spacing))) if spacing < 0 else 0
        qss = f"""
            QTextEdit {{
                background: transparent;
                color: {color};
                font-family: {family};
                font-size: {size}pt;
                border: none;
                padding: {pad_top}px 0px 0px 0px;
                selection-background-color: transparent;
                selection-color: {color};
            }}
        """
        if scrollbar:
            qss += _SCROLLBAR_QSS.format(
                width=scrollbar_width,
                handle=Theme.primaryBorder,
                radius=scrollbar_width // 2,
            )
        self.setStyleSheet(qss)

        # ── Selection colors ──────────────────────────────────────────────
        #    We paint our own tight selection highlight in paintEvent so that
        #    the highlight only covers text metrics, not line spacing.  The
        #    built-in Qt selection is made invisible here; the real gradient
        #    and text color are stored for use by our custom painter.
        self._sel_brush      = QBrush(QColor(Theme.aboutSelectionFontColor))
        self._sel_text_color = QColor(color)

        pal = self.palette()
        # Invisible built-in highlight — our paintEvent draws the real one
        pal.setBrush(QPalette.Highlight,       QBrush(QColor(0, 0, 0, 0)))
        pal.setColor(QPalette.HighlightedText, QColor(color))
        self.setPalette(pal)

        # ── Kill internal margins so text aligns with painted drawText ────
        self.document().setDocumentMargin(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)

        # ── Override line height to tame fonts with inflated metrics ──────
        self._applyLineHeight()
        self.document().blockCountChanged.connect(lambda _: self._applyLineHeight())

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
        """Apply line height from Theme using line_spacing."""
        spacing = Theme.aboutLineSpacing
        if not spacing:
            return
        # LineDistanceHeight adds (or subtracts) pixels between lines,
        # which works for both positive and negative values unlike
        # FixedHeight which Qt clamps at the font's natural metrics.
        fmt = QTextBlockFormat()
        fmt.setLineHeight(spacing, QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value)
        # Apply to every existing block AND the empty first block so newly
        # typed / pasted text inherits the same fixed line height.
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.mergeBlockFormat(fmt)
        # Also format the very first block (covers the empty-document case
        # where Start→End selects nothing).
        cursor.movePosition(QTextCursor.Start)
        cursor.mergeBlockFormat(fmt)

    # ─────────────────────────────────────────────────────────────────────────
    # TIGHT SELECTION HIGHLIGHT
    # ─────────────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        """Paint with tight selection highlights that cover only the text
        metrics height, ignoring any extra line spacing."""
        super().paintEvent(event)

        tc = self.textCursor()
        if not tc.hasSelection():
            return

        sel_start = tc.selectionStart()
        sel_end   = tc.selectionEnd()

        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)

        doc = self.document()
        fm  = self.fontMetrics()
        text_h = fm.ascent() + fm.descent() + Theme.aboutSelectionLineHeight

        sb_v = self.verticalScrollBar()
        sb_h = self.horizontalScrollBar()
        sy = sb_v.value() if sb_v else 0
        sx = sb_h.value() if sb_h else 0

        # ── Content offset: Qt may render the document shifted from (0,0)
        #    (e.g. CSS padding, internal margins).  Compare where Qt places a
        #    cursor vs where blockBoundingRect says it should be so our
        #    highlight lines up with the real glyphs.
        first = doc.firstBlock()
        if first.isValid():
            ref_cursor = QTextCursor(first)
            cr = self.cursorRect(ref_cursor)
            dr = doc.documentLayout().blockBoundingRect(first)
            oy = cr.y() - (dr.y() - sy)
            ox = cr.x() - (dr.x() - sx)
        else:
            oy = ox = 0

        block = doc.findBlock(sel_start)
        while block.isValid() and block.position() < sel_end:
            bl = block.layout()
            if not bl or bl.lineCount() == 0:
                block = block.next()
                continue

            br = doc.documentLayout().blockBoundingRect(block)
            bx = br.x() - sx + ox
            by = br.y() - sy + oy

            # ── Collect tight rects and paint highlight background ────────
            rects = []
            for i in range(bl.lineCount()):
                line = bl.lineAt(i)
                ls = block.position() + line.textStart()
                le = ls + line.textLength()
                if le <= sel_start or ls >= sel_end:
                    continue

                local_s = max(sel_start, ls) - block.position()
                local_e = min(sel_end,   le) - block.position()
                x1 = line.cursorToX(local_s)[0]
                x2 = line.cursorToX(local_e)[0]
                if x2 < x1:
                    x1, x2 = x2, x1

                line_y = by + line.y()
                adj    = Theme.aboutSelectionLineHeight
                top_y  = line_y + (-adj if adj < 0 else 0)

                r = QRectF(bx + x1, top_y, x2 - x1, text_h)
                rects.append(r)
                p.fillRect(r, self._sel_brush)

            # ── Redraw selected glyphs in highlight text color ────────────
            if rects:
                clip = QPainterPath()
                for r in rects:
                    clip.addRect(r)

                local_start = max(sel_start, block.position()) - block.position()
                local_end   = min(sel_end, block.position() + block.length() - 1) - block.position()

                if local_end > local_start:
                    fmt = QTextCharFormat()
                    fmt.setForeground(self._sel_text_color)
                    fr = QTextLayout.FormatRange()
                    fr.start  = local_start
                    fr.length = local_end - local_start
                    fr.format = fmt

                    p.save()
                    p.setClipPath(clip)
                    bl.draw(p, QPointF(bx, by), [fr])
                    p.restore()

            block = block.next()

        p.end()

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
