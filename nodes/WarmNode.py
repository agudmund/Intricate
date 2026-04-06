#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/WarmNode.py WarmNode class
-The main content node. Free-form text with an emoji accent and editable title, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import subprocess
from PySide6.QtWidgets import QGraphicsProxyWidget
from pretty_widgets.PrettyMenu import StyledTextEdit as QTextEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.WarmNodeData import WarmNodeData
from graphics.Theme import Theme


# Layout constants
EMOJI_SIZE      = 28.0      # Emoji accent area at top-left
TITLE_HEIGHT    = 22.0      # Title band below emoji row
PADDING         = 10.0      # General internal padding
BODY_TOP        = PADDING + EMOJI_SIZE + 4.0    # Body text starts here


class WarmNode(BaseNode):
    """
    The main content node — the star of the show.

    Layout (top to bottom):
        ── emoji + title row ──
        ── body text area (QTextEdit proxy, editable) ──

    Double-click anywhere in the body area activates the text editor.
    The title is painted directly and edited via double-click on the title zone.
    The emoji is painted as an accent — changeable via future emoji picker.

    Serialization:
        body_text and emoji are stored in WarmNodeData.
        Both survive session save/load cleanly.
    """

    _has_depth_toggle = True

    def __init__(self, data: WarmNodeData | None = None):
        if data is None:
            data = WarmNodeData()
        super().__init__(data)

        # ── Body text editor ──────────────────────────────────────────────────
        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_body_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT ZONES
    # ─────────────────────────────────────────────────────────────────────────

    def _body_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + PADDING,
            r.y() + BODY_TOP,
            r.width()  - PADDING * 2,
            r.height() - BODY_TOP - PADDING,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BODY EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_body_editor(self) -> None:
        """Build the QTextEdit proxy, hidden until double-clicked."""
        self._editor = QTextEdit()
        self._editor.setFrameStyle(0)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: none;
                padding: 12px 0px 0px 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.setPlainText(self.data.body_text)
        self._editor.textChanged.connect(self._on_text_changed)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.setGeometry(self._body_rect())
        self._editor_proxy.show()   # WarmNode shows editor by default — it IS the content

    def _on_text_changed(self) -> None:
        """Sync text to data on every keystroke — no explicit commit needed."""
        if self._editor:
            self.data.body_text = self._editor.toPlainText()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def _launch_editor(self) -> None:
        """
        Launch the external warm node editor as a peer process.

        Path is read from settings.toml [apps] warm_editor at call time —
        never cached, so changing the path in The Settlers takes effect
        immediately without restarting Intricate.

        Falls back to notepad.exe if no path is configured.
        Fires and forgets — Intricate doesn't own the child process.
        """
        import utils.settings as _settings
        editor_path = _settings.get("apps", "warm_editor", "").strip()
        if not editor_path:
            editor_path = "NotepadPlusPlusDuplexPlusTurbo.exe"
        try:
            from utils.logger import setup_logger
            _log = setup_logger("warmnode")
        except Exception:
            _log = None

        try:
            subprocess.Popen(editor_path, shell=True)
            if _log:
                _log.debug(f"[WarmNode] Launched editor: '{editor_path}'")
            # Roll up the canvas so the editor gets focus
            self._roll_up_curtains()
        except Exception as e:
            if _log:
                _log.warning(f"[WarmNode] Failed to launch '{editor_path}': {e}")

    def _roll_up_curtains(self) -> None:
        """Collapse the main window to its HUD strip so the editor gets focus."""
        try:
            views = self.scene().views() if self.scene() else []
            if not views:
                return
            win = views[0].window()
            if hasattr(win, 'is_collapsed') and not win.is_collapsed:
                win.toggle_curtains()
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event) -> None:
        """
        Route double-click by zone:

            Title zone  → launch external editor (Notepad++ Duplex+ or fallback)
            Body zone   → focus the inline QTextEdit editor
        """
        pos = event.pos()

        if self._title_rect().contains(pos):
            self._launch_editor()
            event.accept()
            return

        if self._body_rect().contains(pos):
            if self.scene() and self.scene().views():
                self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
            self._editor_proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        """Restore view focus policy when the node loses focus."""
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        super().focusOutEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        # Emoji + title — fully delegated to BaseNode
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if self._editor_proxy:
            self._editor_proxy.setGeometry(self._body_rect())

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

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'WarmNode':
        return WarmNode(WarmNodeData.from_dict(data))
