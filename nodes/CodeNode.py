#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/CodeNode.py CodeNode class
-Syntax-highlighted code display node with monospace font, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QSyntaxHighlighter, QTextCharFormat, QFont
from PySide6.QtWidgets import QFileDialog, QGraphicsSceneDragDropEvent

from nodes.BaseNode import BaseNode
from data.CodeNodeData import CodeNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit
from shared_braincell.logger import setup_logger

_log = setup_logger("code")

_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_CODE_FONT     = "Consolas"
_CODE_SIZE     = 9

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json", ".xml",
    ".yaml", ".yml", ".toml", ".sh", ".bat", ".sql", ".md", ".txt",
    ".cfg", ".ini", ".log", ".r", ".swift", ".kt", ".lua", ".pl",
}

_CODE_FILTER = "Code Files (" + " ".join(f"*{ext}" for ext in sorted(_CODE_EXTENSIONS)) + ")"


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
    Supports drag-and-drop of code files from Explorer and a file browser
    via the shelf button.

    Adopts the AboutNode/PaletteNode resize-handle shelf gesture: buttons
    start collapsed and surface only when the user yanks the resize handle
    past the reveal threshold (and re-hide on shrink past the hide
    threshold). The editor breathes with the shelf via _on_shelf_tick.
    """
    _has_depth_toggle = True

    # Shelf reveal/hide thresholds — match AboutNode's asymmetric pair so
    # the gesture feel is consistent across the family that has migrated
    # to the resize-handle pattern.
    _RESIZE_SHELF_REVEAL_THRESHOLD = 75.0
    _RESIZE_SHELF_HIDE_THRESHOLD   = 30.0

    def __init__(self, data: CodeNodeData | None = None):
        if data is None:
            data = CodeNodeData()
        super().__init__(data)

        self.setAcceptDrops(True)
        self.setBrush(self._bg_color())
        self._min_height = Theme.aboutMinHeight
        self._apply_depth()

        # Start with the shelf collapsed — CodeNode adopts AboutNode's
        # resize-handle reveal/hide gesture (mouseMoveEvent below) in
        # place of the legacy double-click toggle. Buttons surface only
        # when the user yanks the resize handle past the reveal threshold.
        self._buttons_visible = False
        self._anim_top_offset = self._HIDDEN_TOP_OFFSET
        for btn in self._buttons:
            btn.hide()
        self._shelf_anchor_h: float | None = None

        self._editor: PrettyEdit | None = None
        self._highlighter: CodeHighlighter | None = None
        self._build_editor()

        # Restore from source_path if label is empty (session reload)
        if not self.data.label and self.data.source_path:
            self._reload_from_source()

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

    def _build_editor(self) -> None:
        # spellcheck=False — CodeNode's whole reason to exist is the syntax
        # highlighter below, and Qt allows only one QSyntaxHighlighter per
        # document. PrettyEdit's always_visible branch auto-attaches its
        # DebouncedSpellHighlighter at end of __init__; without opting out
        # here, that auto-attach displaces CodeHighlighter and we lose all
        # syntax colour AND get red squiggles on every identifier (because
        # code isn't English prose). TreeNode opted out for the same reason
        # 2026-05-02; this is the matching opt-out for the code editor.
        self._editor = PrettyEdit(
            self,
            font_family=_CODE_FONT,
            font_size=_CODE_SIZE,
            font_color=Theme.nodeFontColor,
            always_visible=True,
            spellcheck=False,
        )
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._position_editor()

        # Attach syntax highlighter to the underlying QTextEdit's document.
        # With spellcheck=False above, this is the sole QSyntaxHighlighter
        # on the document and runs unchallenged.
        self._highlighter = CodeHighlighter(self._editor.document())

    def _on_text_changed(self) -> None:
        self.data.label = self._editor.toPlainText()

    def _position_editor(self) -> None:
        # Use _anim_top_offset (not the static _BUTTON_ZONE_H) so the
        # editor breathes with the shelf reveal/hide animation. When the
        # shelf is hidden the offset is _HIDDEN_TOP_OFFSET (~8 px) and
        # the editor occupies almost the entire node; when revealed the
        # offset animates up to _BUTTON_ZONE_H and the editor shrinks
        # to make room for the button strip.
        r = self.rect()
        top = self._anim_top_offset
        self._editor.position(QRectF(
            r.left()  + _PAD,
            r.top()   + top,
            r.width() - _PAD * 2,
            r.height() - top - _PAD,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # FILE LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """Read a code file from disk and populate the editor."""
        path = Path(path)
        if not path.is_file():
            _log.warning(f"[CodeNode] file not found: {path}")
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            _log.warning(f"[CodeNode] failed to read {path}: {e}")
            return

        self.data.source_path = str(path.resolve())
        self.data.label = text
        self.data.title = path.name
        if self._editor:
            self._editor.blockSignals(True)
            self._editor.setPlainText(text)
            self._editor.blockSignals(False)
        self.update()
        _log.info(f"[CodeNode] loaded {path.name} ({len(text)} chars)")

    def _reload_from_source(self) -> None:
        """Reload content from source_path (used on session restore).

        Deliberately uses load_from_path rather than load_from_path_and_fit —
        on restore the saved geometry is authoritative; the user may have
        manually corner-dragged the node smaller than the content (cropping
        for canvas tidiness) and a fit-on-restore would silently undo that.
        """
        p = Path(self.data.source_path)
        if p.is_file():
            self.load_from_path(p)
        else:
            _log.warning(f"[CodeNode] source_path missing on restore: {p}")

    def load_from_path_and_fit(self, path: str | Path) -> None:
        """User-initiated file load: read content + grow node to fit.

        Convenience entry point for any user-driven caller (drag-drop,
        file-browser button, future callers) that wants the node to size
        itself to the content. Restore deliberately uses ``load_from_path``
        alone so saved geometry is preserved.
        """
        self.load_from_path(path)
        self._auto_fit_to_content()

    def _auto_fit_to_content(self) -> None:
        """Resize the node to fit the loaded content — grow-only, no upper cap.

        Width grows to the longest line's natural width; height grows to
        the full document height plus the title strip and bottom padding.
        Preserves any manual corner-drag larger than the content (grow-
        only), and has no upper bound — per the spatial workflow, a
        5,000-line file rightfully spawns a node huge in proportion to
        its tiny neighbours, since scale is the user's primary cognitive
        sort dimension on the canvas.
        """
        if not self._editor:
            return
        doc = self._editor.document()

        # Measure at unconstrained width to get the longest line's
        # natural width, then re-layout at that width to read the true
        # document height. Restore the previous text width afterwards
        # so subsequent setRect re-layouts cleanly.
        prev_tw = doc.textWidth()
        doc.setTextWidth(-1)
        ideal_w = doc.idealWidth()
        doc.setTextWidth(ideal_w)
        doc_h = doc.size().height()
        doc.setTextWidth(prev_tw)

        # Chrome accounting matches _position_editor: side padding both
        # sides + button strip + bottom padding, plus a small breathing
        # buffer so the last line isn't flush against the rect edge.
        needed_w = ideal_w + _PAD * 2 + 8
        needed_h = doc_h   + _BUTTON_ZONE_H + _PAD + 12

        cur = self.rect()
        new_w = max(cur.width(),  needed_w)
        new_h = max(cur.height(), needed_h)

        if abs(new_w - cur.width()) < 1 and abs(new_h - cur.height()) < 1:
            return  # nothing meaningful changed

        self.prepareGeometryChange()
        self.setRect(QRectF(cur.x(), cur.y(), new_w, new_h))
        self.data.width  = new_w
        self.data.height = new_h
        _log.debug(
            "[CodeNode] auto-fit %.0fx%.0f → %.0fx%.0f (ideal_w=%.0f doc_h=%.0f)",
            cur.width(), cur.height(), new_w, new_h, ideal_w, doc_h,
        )

    def _open_file_browser(self) -> None:
        """Open a file dialog to pick a code file."""
        scene = self.scene()
        start_dir = scene.get_browse_dir("code") if scene else ""
        with self._dialog_choreography() as mw:
            path, _ = QFileDialog.getOpenFileName(
                mw,
                "Select Code File",
                start_dir,
                _CODE_FILTER,
            )
        if path:
            if scene:
                scene.remember_browse_dir("code", str(Path(path).parent))
            self.load_from_path_and_fit(path)
            # Mirror View.dropEvent's secondary spawn — .py source with hex
            # literals gets a PaletteNode satellite alongside the CodeNode.
            # Uses the _from_text variant so we don't re-read the file the
            # loader just pulled into self.data.label.
            if scene and Path(path).suffix.lower() == ".py":
                from utils.palette_satellite import spawn_palette_satellite_from_text
                spawn_palette_satellite_from_text(scene, self, self.data.label)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        super()._build_buttons()
        from nodes.NodeButton import NodeButton

        browse_pix = Theme.icon(Theme.iconCodeBrowse, fallback_color="#9ab8d9")
        browse_btn = NodeButton(self, browse_pix, self._open_file_browser)
        browse_btn.setToolTip("Browse for a code file")
        self._buttons.append(browse_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # DRAG AND DROP
    # ─────────────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in _CODE_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        """Drop a code file onto an existing CodeNode to load it."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in _CODE_EXTENSIONS:
                self.load_from_path(path)
                event.acceptProposedAction()
                return
        event.ignore()

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

    # ── Shelf reveal/hide via resize-handle gesture ─────────────────────────
    # Mirrors AboutNode's bidirectional shelf coupling. _shelf_anchor_h is
    # seeded on every press and re-seeded after every toggle so a single
    # continuous drag can flip the shelf multiple times.

    def mousePressEvent(self, event) -> None:
        # Seed the shelf anchor at the start of any drag so the first
        # threshold check measures from press-time height.
        self._shelf_anchor_h = self.rect().height()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # Defer to BaseNode first so the resize actually happens and
        # self.rect() reflects the updated geometry before we inspect it.
        super().mouseMoveEvent(event)
        if not self._is_resizing:
            return
        if self._shelf_anchor_h is None:
            self._shelf_anchor_h = self.rect().height()
        delta_h = self.rect().height() - self._shelf_anchor_h
        if not self._buttons_visible and delta_h > self._RESIZE_SHELF_REVEAL_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()
        elif self._buttons_visible and delta_h < -self._RESIZE_SHELF_HIDE_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()

    def _on_shelf_tick(self, value: float) -> None:
        # Reposition the editor on every animation frame so it grows /
        # shrinks smoothly with the shelf reveal / hide. BaseNode's tick
        # updates _anim_top_offset and triggers a repaint; we add the
        # editor reposition on top.
        super()._on_shelf_tick(value)
        if self._editor:
            self._position_editor()

    def mouseDoubleClickEvent(self, event) -> None:
        # Double-click on the node body falls through to focus the editor —
        # rare in practice because the always-visible PrettyEdit fills most
        # of the rect and absorbs its own clicks, but keeps the padding
        # around the editor as an affordance to drop focus into the text.
        #
        # Deliberately does NOT call super() — BaseNode's default toggles
        # the shelf on top-strip double-click, which is the legacy pattern
        # CodeNode replaced with the resize-handle gesture (mouseMoveEvent
        # above). The previous title-strip → file-browser shortcut was
        # also removed in the same pass: file browse is now exclusively
        # via the shelf button (revealed by the resize-handle gesture).
        # Spatial-canvas-native vs framework-leakage — a click is not a
        # gesture; the gesture goes through the resize handle we already
        # grab to dial the node's size anyway.
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

    def _demolition_pre(self) -> None:
        self._highlighter = None
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
    def from_dict(data: dict) -> 'CodeNode':
        return CodeNode(CodeNodeData.from_dict(data))
