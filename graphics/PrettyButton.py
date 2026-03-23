#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Button
-The last of the pretty buttons knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from graphics.Theme import Theme

class PrettyButton(QPushButton):
    """
    A warm and pretty button with its own specific defaults 🌿
    """
    def __init__(self, text="yay! 🌿", parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumWidth(Theme.buttonMinWidth)
        self.setMinimumHeight(Theme.buttonMinHeight)

        # Apply our Python-driven styles
        self.update_style()

        font = self.font()
        font.setFamily(Theme.buttonFontFamily)
        font.setPointSize(Theme.buttonFontSize)
        font.setBold(Theme.buttonFontBold)
        self.setFont(font)

    def update_style(self):
        # We use HexArgb to ensure that if we add transparency to the theme later,
        # the stylesheet actually respects the alpha channel.
        base_padding = 5
        top_padding = base_padding + Theme.buttonTextVerticalOffset
        bottom_padding = base_padding - Theme.buttonTextVerticalOffset

        # Clamp to ensure we never have negative padding
        top_padding = max(0, top_padding)
        bottom_padding = max(0, bottom_padding)

        # Theme-driven border logic
        # background-color: {Theme.buttonBg};
        border_width = Theme.buttonBorderWidth if Theme.buttonBorderEnabled else 0

        self.setStyleSheet(f"""
           QPushButton {{
               background-color: {Theme.buttonBg};
               border: {border_width}px solid {Theme.buttonBorder};
               border-radius: 6px;
               color: {Theme.textPrimary};
               padding: {top_padding}px 15px {bottom_padding}px 15px;
           }}
        """)
        

def button(
    text: str = "yay! 🌿",
    parent=None,
    **kwargs
) -> QPushButton:
    """
    Creates a fresh pretty button ready for layouts.
    Special support for 'clicked=slot' (connects the clicked signal).
    Other kwargs are passed to setters (e.g. fixedWidth=120, icon=..., etc.)
    """
    btn = PrettyButton(text, parent)

    # Handle signal connections first
    if "clicked" in kwargs:
        slot = kwargs.pop("clicked")
        if slot is not None:
            btn.clicked.connect(slot)

    # Then apply remaining kwargs as setters
    for key, value in kwargs.items():
        setter_name = f"set{key[0].upper() + key[1:]}"
        setter = getattr(btn, setter_name, None)
        if setter and callable(setter):
            setter(value)

    return btn