#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - main_window.py main application window
-One day it woke up and dreamt of becoming a frameless window with draggable toolbars and a node graphics view for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QComboBox, QGraphicsScene, QGraphicsView
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QSize, QRect
from graphics.Scene import IntricateScene
from graphics.View import IntricateView

class Theme:

    # =========================================================================
    # GLOBAL
    # =========================================================================

    windowBg                = "#282828"         # The primary window background color
    primaryBorder           = "#6b5a47"         # Applies to mostly all lines drawn across the Ui
    textPrimary             = "#d2d1cf"         # Primary ivory/warm white — buttons, labels, general UI text
    backDrop                = "#00d2ff"         # Primary component background color
    windowBorderWidth       = 1
    toolbarBorder           = primaryBorder
    layoutMargins           = (10, 5, 10, 5)    # Unified margins for all layouts to ensure the Grid remains symmetrical
    handleHeightTop         = 35                # Top toolbar/title bar height (draggable area)
    handleHeightBottom      = 100               # Bottom toolbar/button bar height

    # =========================================================================
    # BUTTONS
    # =========================================================================

    buttonPrimaryColor = windowBg
    buttonInactiveColor = "#1f1f1f"

    buttonFontFamily         = "Reey"
    buttonFontSize           = 22
    buttonFontBold           = False
    buttonTextVerticalOffset = -2
    buttonBorderWidth        = 1
    buttonBorderEnabled      = False
    buttonMinWidth           = 160
    buttonMinHeight          = 75

    buttonBg                = buttonPrimaryColor
    buttonBgHover           = buttonPrimaryColor
    buttonBgInactive        = buttonInactiveColor

    buttonBorder            = primaryBorder
    buttonBorderHover       = primaryBorder
    buttonBorderInactive    = buttonInactiveColor

    # --- Icon-Only Button Settings ---
    iconButtonSize          = handleHeightTop - 3
    iconPadding             = 12   # Padding inside the button for the .png
    iconPathImage           = "iconic.png" 

    # =========================================================================
    # COMBOBOX
    # =========================================================================

    comboboxBg            = windowBg
    comboboxBgOpen        = "#2a2a3a"
    comboboxText          = textPrimary
    comboboxBorder        = primaryBorder
    comboboxBorderRadius  = 9
    comboboxPadding       = "3px 12px"
    comboboxFontFamily    = "Segoe UI"
    comboboxFontSize      = 9
    comboboxFontWeight    = "normal"
    comboboxDropdownWidth = 30
    comboboxMinWidth      = 350

    # Helper for hex conversion
    def to_hex(color): return color.name(QColor.HexArgb)


class PrettyButton(QPushButton):
    """
    A warm and pretty button with its own specific defaults 🌿
    """
    def __init__(self, text="yay! 🌿", parent=None):
        super().__init__(text, parent)
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

class NodeScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-1000, -1000, 1000, 1000)

class IntricateApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 1. The civil pleasantries
        self.setWindowTitle("Our Love As Intricate As The Patterns We Impose")
        self.setStyleSheet(f"QMainWindow {{ background-color: {Theme.windowBg}; }}")
        self.setWindowOpacity(0.0)

        # 2. The Beautiful and Prestigious Top Toolbar things with all it's specifics
        self._dragging_window = False
        self._drag_pos = None
        self.is_collapsed = False

        # 3.  Window OS Defaults
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # self.setAttribute(Qt.WA_TranslucentBackground) # this is for the selective blur later
        self.setMinimumSize(500, 500)
        
        # 4. Grid and widget setup
        self._setup_grid()
        self._setupTopToolbar()
        self._setupTheAreaFormerlyKnownAsNodal()
        self._setupBottomToolbar()

    def _setup_grid(self):
        """
        3-row grid — the permanent skeleton of the window.

        Row 0: topToolbar    — fixed height, anchored to top
        Row 1: central       — stretches to fill all available space
        Row 2: bottomToolbar — fixed height, anchored to bottom

        The central widget holds the grid; each shelf is a QWidget
        dropped into its row. Toolbars fix their height via setFixedHeight;
        the canvas row gets stretch factor 1 so it expands with the window.
        """

        self._root = QWidget()
        self.setCentralWidget(self._root)

        self.grid = QGridLayout(self._root)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        # Row 1 (canvas) takes all the vertical slack
        self.grid.setRowStretch(1, 1)

    # =========================================================================
    # The top toolbar with all the fancy features
    # =========================================================================

    def _setupTopToolbar(self):
        self.topToolbar = QWidget()
        self.topToolbar.setFixedHeight(Theme.handleHeightTop)

        layout = QHBoxLayout(self.topToolbar)
        layout.setContentsMargins(*Theme.layoutMargins)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)
        layout.addStretch()
        layout.addWidget(self.setup_project_selector())
        layout.addWidget(self.setup_iconic_button(clicked=self.toggle_curtains))
        layout.addStretch()

        self.grid.addWidget(self.topToolbar, 0, 0)

    def setup_project_selector(self):
        """The Project Selector Combo Box"""

        self.project_selector = QComboBox()
        self.project_selector.setObjectName("project_selector")

        # Apply theme-driven stylesheet
        self.project_selector.setMinimumWidth(Theme.comboboxMinWidth)
        self.project_selector.setStyleSheet(f"""
            QComboBox#project_selector {{
                background-color: {Theme.comboboxBg};
                color: {Theme.comboboxText};
                border: 1px solid {Theme.comboboxBorder};
                border-radius: {Theme.comboboxBorderRadius}px;
                padding: {Theme.comboboxPadding};
                font-family: {Theme.comboboxFontFamily};
                font-size: {Theme.comboboxFontSize}pt;
                font-weight: {Theme.comboboxFontWeight};
            }}
            QComboBox#project_selector::drop-down {{
                border: none;
                width: {Theme.comboboxDropdownWidth}px;
            }}
            QComboBox#project_selector QAbstractItemView {{
                background-color: {Theme.comboboxBgOpen};
                color: {Theme.comboboxText};
                border: 1px solid {Theme.comboboxBorder};
                selection-background-color: {Theme.backDrop};
                font-family: {Theme.comboboxFontFamily};
                font-size: {Theme.comboboxFontSize}pt;
            }}
        """)

        # Make sure that the sessions are populated before connecting the signal otherwise the literal seventh level of hades arrives needing over 200 lines of code to account for disabling and enabling the session list
        self.populate_sessions()
        self.project_selector.currentIndexChanged.connect(self.on_session_changed)

        return self.project_selector

    def setup_iconic_button(self, clicked=None):
            """Creates a square, icon-only version of PrettyButton"""
            
            # Pass empty string to avoid CozyButton's default text-padding logic
            btn = PrettyButton("", self)
            
            # Set absolute square dimensions to match ComboBox height
            btn.setFixedSize(QSize(Theme.iconButtonSize, Theme.iconButtonSize))
            
            # Apply the icon
            btn.setIcon(QIcon(Theme.iconPathImage))
            btn.setIconSize(QSize(Theme.iconButtonSize - Theme.iconPadding, 
                                  Theme.iconButtonSize - Theme.iconPadding))
            
            # Override the horizontal padding of 15px from PrettyButton
            btn.setStyleSheet(btn.styleSheet())
            
            # Connect to your future node logic
            btn.clicked.connect(clicked) 
            
            return btn

    # =========================================================================
    # Curtains, The Window Rollup Thing
    # =========================================================================

    def toggle_curtains(self):
        """Animate the window into a sleek HUD strip."""
        self.setMinimumHeight(0)
        self.curtain_anim = QPropertyAnimation(self, b"geometry")
        self.curtain_anim.setDuration(450)
        self.curtain_anim.setEasingCurve(QEasingCurve.OutExpo)

        start_rect = self.geometry()
        
        if not self.is_collapsed:

            # --- Pull up the Curtains ---
            self.original_height = self.height()
            # Collapse to exactly the draggable top-bar height
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), Theme.handleHeightTop)
            
            # Fade out the canvas to keep the HUD clean
            self.central.hide()
            self.bottomToolbar.hide()

        else:
            # --- Open the Curtains ---
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), self.original_height)
            self.central.show()
            self.bottomToolbar.show()

        self.curtain_anim.setStartValue(start_rect)
        self.curtain_anim.setEndValue(end_rect)
        self.curtain_anim.start()
        
        self.is_collapsed = not self.is_collapsed


    # =========================================================================
    # The ten minutes of play time central area
    # =========================================================================

    def _setupTheAreaFormerlyKnownAsNodal(self):
        self.central = QWidget()
        self.scene = IntricateScene()
        self.view = IntricateView(self.scene)

        layout = QHBoxLayout(self.central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)

        self.grid.addWidget(self.central, 1, 0)

    # =========================================================================
    # The buttons and stuff at the bottom of the Ui
    # =========================================================================

    def _setupBottomToolbar(self):
        self.bottomToolbar = QWidget()
        self.bottomToolbar.setFixedHeight(Theme.handleHeightBottom)

        layout = QHBoxLayout(self.bottomToolbar)
        layout.setContentsMargins(*Theme.layoutMargins)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)
        layout.addStretch()
        layout.addWidget(button("Exid", clicked=self.close))        # Note: "Exid" is not a typo - it's an exit button named exid

        self.grid.addWidget(self.bottomToolbar, 2, 0)

    # =========================================================================
    # Sessions
    # =========================================================================

    def on_session_changed(self):
        print('Joy buckets are still not filling, keep going you got this!')

    def populate_sessions(self):
        motivationalMessages = [
            "All Glory",
            "Practical and pleasurable",
            "Tiny little extra sprinkles of joy",
            "Irresistible",
            "Sweet",
            "Soft",
            "New Thought",
            "Delicate",
            "Gentle",
            "Intentional",
            "Pure Light",
            "Fresh Start",
            "Endless Potential",
            "Golden Hour",
            "Growth",
            "Boundless Joy",
            "Infinite Wisdom",
            "Onward",
            "Clear Vision",
            "Bright Tomorrow",
            "Inner Peace",
            "Clay",
            "Omnious",
            "Intricate",
            "Bloom",
            "Unfold",
            "Evolve",
            "Beautiful",
            "Elegant",
            "Grace",
            "Accurate",
            "Kinetic",
        ]
        self.project_selector.addItems(motivationalMessages)

    # =========================================================================
    # Mouse and Hover Events
    # =========================================================================

    def mousePressEvent(self, event):
        """The Curtains Sensor: Every single press counts. (coming soon!)"""
        if event.button() == Qt.LeftButton and event.position().y() < Theme.handleHeightTop:
            
            # Positional Replacement is probably the most overcomplicated way to phrase what this feature does
            self._dragging_window = True
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Move window gently when dragging the top bar."""
        if self._dragging_window:
            new_pos = event.globalPosition().toPoint()
            self.move(self.pos() + (new_pos - self._drag_pos))
            self._drag_pos = new_pos
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Release the window to let it enjoy it's new location."""
        self._dragging_window = False
        super().mouseReleaseEvent(event)

    # =========================================================================
    # App Core Events
    # =========================================================================

    def showEvent(self, event):
        """
        This ensures the window fades in as the Star that it is rather than just popping into existence.
        """
        super().showEvent(event)
        
        # We use a ParallelAnimationGroup to ensure the opacity 
        # is driven specifically and cleanly
        self.fadeIn = QPropertyAnimation(self, b"windowOpacity")
        self.fadeIn.setDuration(500)
        self.fadeIn.setStartValue(0.0)
        self.fadeIn.setEndValue(1.0)
        self.fadeIn.setEasingCurve(QEasingCurve.OutCubic) # Smooth deceleration
        self.fadeIn.start()

    def closeEvent(self, event):
        """
        It should be a joyful moment because now we can look forward to seeing each other later.
        """
        if self.windowOpacity() <= 0.0:
            event.accept()
            return

        event.ignore()
        
        self.fadeOut = QPropertyAnimation(self, b"windowOpacity")
        self.fadeOut.setDuration(300)
        self.fadeOut.setStartValue(self.windowOpacity())
        self.fadeOut.setEndValue(0.0)
        self.fadeOut.setEasingCurve(QEasingCurve.InCubic)
        self.fadeOut.finished.connect(self.close) 
        self.fadeOut.start()

        print(f"Exid: Intricate will be back as soon as we can! ✨")