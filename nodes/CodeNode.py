#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/CodeNode.py CodeNode class
-Syntax-highlighted code display node with monospace font, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QSyntaxHighlighter, QTextCharFormat, QFont

from nodes.BaseNode import BaseNode
from data.CodeNodeData import CodeNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_CODE_FONT     = "Consolas"
_CODE_SIZE     = 9


# ─────────────────────────────────────────────────────────────────────────────
# SYNTAX HIGHLIGHTER
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(hex_color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(hex_color))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFont(QFont(_CODE_FONT, _CODE_SIZE, italic=True))
    return f


class CodeHighlighter(QSyntaxHighlighter):
    """Generic multi-language syntax highlighter with warm dark-theme colors."""

    # ── Color palette ────────────────────────────────────────────────────────
    _KEYWORD    = _fmt("#c586c0", bold=True)     # purple-pink — keywords
    _BUILTIN    = _fmt("#d4a0c0")                # soft pink — self, True, False, None
    _STRING     = _fmt("#ce9178")                # warm orange — strings
    _COMMENT    = _fmt("#6a9955", italic=True)    # muted green — comments
    _NUMBER     = _fmt("#b5cea8")                # light green — numbers
    _FUNCTION   = _fmt("#dcdcaa")                # gold — function names
    _DECORATOR  = _fmt("#4ec9b0")                # teal — decorators
    _OPERATOR   = _fmt("#d4d4d4")                # light gray — operators
    _CLASS      = _fmt("#4ec9b0", bold=True)      # teal bold — class names

    # ── Patterns (compiled once) ─────────────────────────────────────────────
    _KEYWORDS = (
        r'\b(?:def|class|if|elif|else|for|while|return|import|from|as|with|'
        r'try|except|finally|raise|yield|lambda|pass|break|continue|del|in|'
        r'not|and|or|is|assert|global|nonlocal|async|await|'
        # JS / C-like
        r'function|var|let|const|new|this|typeof|instanceof|void|'
        r'switch|case|default|throw|catch|static|extends|super|'
        r'int|float|double|char|bool|string|struct|enum|public|private|'
        r'protected|virtual|override|namespace|using|include|pragma)\b'
    )
    _BUILTINS = r'\b(?:self|cls|True|False|None|true|false|null|undefined|NaN|print|len|range|type|str|int|float|list|dict|set|tuple|map|filter|super)\b'

    _RULES = None  # lazily compiled

    @classmethod
    def _compile_rules(cls):
        if cls._RULES is not None:
            return
        cls._RULES = [
            (re.compile(cls._KEYWORDS),                          cls._KEYWORD),
            (re.compile(cls._BUILTINS),                          cls._BUILTIN),
            (re.compile(r'@\w+'),                                cls._DECORATOR),
            (re.compile(r'\b[A-Z]\w*(?=\s*[:(])'),               cls._CLASS),
            (re.compile(r'(?<=\bdef\s)\w+'),                     cls._FUNCTION),
            (re.compile(r'(?<=\bclass\s)\w+'),                   cls._CLASS),
            (re.compile(r'\b\d+\.?\d*(?:[eE][+-]?\d+)?\b'),      cls._NUMBER),
            (re.compile(r'0[xX][0-9a-fA-F]+'),                   cls._NUMBER),
            (re.compile(r'[+\-*/%=<>!&|^~]+'),                   cls._OPERATOR),
        ]
        # String patterns — order matters (triple-quoted before single)
        cls._STRING_PATTERNS = [
            re.compile(r'""".*?"""', re.DOTALL),
            re.compile(r"'''.*?'''", re.DOTALL),
            re.compile(r'"(?:[^"\\]|\\.)*"'),
            re.compile(r"'(?:[^'\\]|\\.)*'"),
            re.compile(r'`(?:[^`\\]|\\.)*`'),        # JS template literals
        ]
        cls._COMMENT_PATTERNS = [
            re.compile(r'#.*$',  re.MULTILINE),      # Python / shell
            re.compile(r'//.*$', re.MULTILINE),       # C / JS
        ]

    def highlightBlock(self, text: str) -> None:
        self.__class__._compile_rules()

        # Apply keyword / number / operator rules
        for pattern, fmt in self._RULES:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Strings (override keywords inside strings)
        for pattern in self._STRING_PATTERNS:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self._STRING)

        # Comments (override everything — highest priority)
        for pattern in self._COMMENT_PATTERNS:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self._COMMENT)


# ─────────────────────────────────────────────────────────────────────────────
# CODE NODE
# ─────────────────────────────────────────────────────────────────────────────

class CodeNode(BaseNode):
    """
    A syntax-highlighted code display node with monospace font.

    Based on the TextNode pattern — always-editable PrettyEdit with a
    CodeHighlighter attached to the editor's document for live coloring.
    """
    _has_depth_toggle = True

    def __init__(self, data: CodeNodeData | None = None):
        if data is None:
            data = CodeNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: PrettyEdit | None = None
        self._highlighter: CodeHighlighter | None = None
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
            font_family=_CODE_FONT,
            font_size=_CODE_SIZE,
            font_color=Theme.nodeFontColor,
            always_visible=True,
        )
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._position_editor()

        # Attach syntax highlighter to the underlying QTextEdit's document
        self._highlighter = CodeHighlighter(self._editor.document())

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
        self._highlighter = None
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
    def from_dict(data: dict) -> 'CodeNode':
        return CodeNode(CodeNodeData.from_dict(data))
