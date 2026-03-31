#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Label
-The last of the pretty labels knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QLabel

from graphics.Theme import Theme
import utils.settings as settings


class PrettyLabel(QLabel):
    """
    A themed QLabel matching the app's default text style.

    Default appearance:
        font-family: Lato, 11px, Theme.textPrimary
        transparent background, no border, 0px 4px padding

    Pass clickable=True to add a pointer cursor, enable mouse interaction,
    and emit the clicked Signal on press — no mousePressEvent monkey-patching
    needed at the call site.
    """

    clicked = Signal()

    def __init__(self, text: str = "", clickable: bool = False, parent=None):
        super().__init__(text, parent)
        self._clickable = clickable
        self._apply_style()
        if clickable:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        color     = settings.get("theme", "ui_label_color", "") or Theme.textPrimary
        font      = settings.get("theme", "ui_font",       "Lato")
        font_size = int(settings.get("theme", "ui_font_size", 11))
        self.setStyleSheet(
            f"QLabel {{"
            f"  background:    transparent;"
            f"  border:        none;"
            f"  border-radius: 0px;"
            f"  padding:       0px 4px;"
            f"  color:         {color};"
            f"  font-size:     {font_size}px;"
            f"  font-family:   {font};"
            f"}}"
        )

    # ── Click handling ────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(event)


def label(
    text: str = "",
    clickable: bool = False,
    parent=None,
    **kwargs,
) -> PrettyLabel:
    """
    Create a themed PrettyLabel.

    Common kwargs:
        clicked      = callable             → clicked.connect(callable)
        alignment    = Qt.AlignmentFlag.*  → setAlignment(...)
        fixedHeight  = int                 → setFixedHeight(int)
        fixedWidth   = int                 → setFixedWidth(int)
    """
    lbl = PrettyLabel(text, clickable=clickable, parent=parent)

    if "clicked" in kwargs:
        slot = kwargs.pop("clicked")
        if slot:
            lbl.clicked.connect(slot)

    for key, value in kwargs.items():
        if not key:
            continue
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(lbl, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettyLabel has no setter for '{key}' (tried {setter_name})")

    return lbl
