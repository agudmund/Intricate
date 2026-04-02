#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Menu
-The last of the pretty menus knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QMenu, QTextEdit, QLineEdit
from graphics.Theme import Theme


# ── Shared stylesheet ────────────────────────────────────────────────────────
# Single source of truth for context-menu styling across the entire app.
# Used directly by PrettyMenu and also exported as menu_stylesheet() so
# PrettyCombo can embed the same QMenu rules inside its own stylesheet.

def menu_stylesheet() -> str:
    """Return the canonical QMenu stylesheet block.

    Callers that embed a QMenu inside a larger stylesheet (e.g. PrettyCombo)
    can splice this string in rather than duplicating the rules.
    """
    return f"""
        QMenu {{
            background:    {Theme.backDrop};
            color:         {Theme.textPrimary};
            border:        1px solid {Theme.primaryBorder};
            border-radius: 9px;
            padding:       4px;
            font-family:   '{Theme.healthFontFamily}';
            font-size:     {Theme.healthFontSizeLabel}pt;
        }}
        QMenu::item {{
            padding:       5px 16px;
            border-radius: 5px;
        }}
        QMenu::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1e1e1e, stop:0.4 #5c3e4f,
                stop:0.7 #a56a85, stop:1 #d87a9e);
        }}
    """


class PrettyMenu(QMenu):
    """A themed QMenu matching the app's visual language."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(menu_stylesheet())


def menu(parent=None) -> PrettyMenu:
    """Create a themed PrettyMenu."""
    return PrettyMenu(parent=parent)


# ── Drop-in replacements for QTextEdit / QLineEdit ──────────────────────────
# These override contextMenuEvent so every right-click menu in the app
# gets PrettyMenu styling automatically — no per-widget wiring needed.

class StyledTextEdit(QTextEdit):
    """QTextEdit whose right-click context menu uses PrettyMenu styling."""

    def contextMenuEvent(self, event):
        ctx = self.createStandardContextMenu()
        ctx.setStyleSheet(menu_stylesheet())
        ctx.exec(event.globalPos())
        ctx.deleteLater()


class StyledLineEdit(QLineEdit):
    """QLineEdit whose right-click context menu uses PrettyMenu styling."""

    def contextMenuEvent(self, event):
        ctx = self.createStandardContextMenu()
        ctx.setStyleSheet(menu_stylesheet())
        ctx.exec(event.globalPos())
        ctx.deleteLater()
