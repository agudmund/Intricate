#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Button
-The last of the pretty buttons knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton
from graphics.Theme import Theme

class PrettyButton(QPushButton):
    """
    A warm and pretty button with its own specific defaults 🌿
    """
    def __init__(self, text="yay! 🌿", icon_name=None, parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumWidth(Theme.buttonMinWidth)
        self.setMinimumHeight(Theme.buttonMinHeight)
        if icon_name:
            self.set_pretty_icon(icon_name)

        # Apply our Python-driven styles
        self.update_style()

        font = self.font()
        font.setFamily(Theme.buttonFontFamily)
        font.setPointSize(Theme.buttonFontSize)
        font.setBold(Theme.buttonFontBold)
        self.setFont(font)

    def set_pretty_icon(self, icon_name):
        """Fetches pixmap from Theme and applies it as a QIcon."""
        pixmap = Theme.icon(icon_name)
        if pixmap:
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(Theme.iconSize, Theme.iconSize))

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
    text: str = None, 
    icon_name: str = None, 
    parent=None, 
    **kwargs
) -> QPushButton:
    """
    Creates a fresh pretty button. 
    Now with intelligent property mapping for ToolTips and Icons.
    """
    # 1. Initialize with our new icon support
    btn = PrettyButton(text or "", icon_name=icon_name, parent=parent)

    # 2. Handle ToolTip casing specifically (Designer-friendly)
    if "tooltip" in kwargs:
        btn.setToolTip(kwargs.pop("tooltip"))

    # 3. Handle signal connections
    if "clicked" in kwargs:
        slot = kwargs.pop("clicked")
        if slot:
            btn.clicked.connect(slot)

    # 4. Apply remaining kwargs as setters (e.g., fixedWidth=120)
    for key, value in kwargs.items():
        # We capitalize the first letter to match Qt's setPropertyName pattern
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(btn, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettyButton has no setter for '{key}' (tried {setter_name})")
            
    return btn