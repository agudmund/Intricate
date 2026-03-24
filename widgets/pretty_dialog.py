#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - widgets/pretty_dialog.py PrettyDialog dialog widget
-Modern, theme-driven dialog with 3x3 grid, draggable top bar, curtains/fade, and eventually a resize grip for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QLabel, QPushButton, QSizeGrip, QSizePolicy
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QSize, QRect,QAbstractAnimation
from PySide6.QtGui import QPainter, QColor, QIcon
from graphics.Theme import Theme
from graphics.PrettyButton import button
from PySide6.QtCore import QParallelAnimationGroup, QPropertyAnimation, QEasingCurve

class PrettyDialog(QWidget): # Switched from QDialog
    def __init__(self, parent=None, title="Dialog"):
        # We use Qt.Window to keep it floating and Qt.FramelessWindowHint for the aesthetic
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)
        
        # This is the 'Secret Sauce' for Curtains:
        # We tell the widget NOT to enforce a minimum size based on its children.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 1. The civil pleasantries - We set this layout once. No inhereted window should ever overwrite this.
        self.main_grid = QGridLayout(self)
        self.main_grid.setContentsMargins(0, 0, 0, 0)
        self.main_grid.setSpacing(0)

        # 2. The Beautiful and Prestigious Top Toolbar things with all it's specifics
        self._dragging_window = False
        self._drag_pos = None
        self.is_collapsed = False
        self.curtain_anim = None
        self.original_height = 400 # Or whatever your default is

        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(Theme.handleHeightTop)
        self.top_bar.setStyleSheet(f"background: {Theme.windowBg}")
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(15, 0, 15, 0)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {Theme.textPrimary}")
        self.top_layout.addWidget(self.title_label)
        self.top_layout.addStretch()

        self.top_layout.addWidget(self.setup_iconic_button(clicked=self.toggle_curtains))
        
        # Add a close button to the template so you don't have to build it every time
        self.close_btn = button("✕", clicked=self.close, fixedWidth=40, fixedHeight=30)
        self.top_layout.addWidget(self.close_btn)

        # --- 3. THE CONTENT ZONE (The Majestic Pearl) ---
        self.central = QWidget()
        self.content_layout = QVBoxLayout(self.central)
        self.content_layout.setContentsMargins(20, 20, 20, 20)

        # Bottom toolbar, it needs to be a 3x3 by default, even if the bottom one is empty in some
        self._setupBottomToolbar()
        
        # --- 4. THE ASSEMBLY ---
        self.main_grid.addWidget(self.top_bar, 0, 0)
        self.main_grid.addWidget(self.central, 1, 0)
        self.main_grid.addWidget(self.bottomToolbar, 2, 0)

    def toggle_curtains(self):
        """The Deterministic And Seriously Nitpicky Perfectionist Refreshing Curtain That Always Gets Results."""
        # 1. State check
        self.curtain_group = QParallelAnimationGroup()
        self.is_collapsed = not self.is_collapsed
        start_geo = self.geometry()
        pace = Theme.windowRollTiming
        
        if self.is_collapsed:
            # 2. Curl up into a comfort security blanket
            self.old_geometry = start_geo
            target_h = Theme.handleHeightTop
            
            self.old_height = self.height()
            target_h = Theme.handleHeightTop # 35px
            end_geo = QRect(start_geo.x(), start_geo.y(), start_geo.width(), target_h)

            # 3. The Spectacle
            self.central.hide()
            if hasattr(self, 'bottomToolbar'): self.bottomToolbar.hide()

            # 4. The secret sauce and the reason why it has every right to act as pretentious as it does: 
            # # We must set the minimumHeight to the target IMMEDIATELY.
            # # This 'unlocks' the OS frame so the swoosh can actually happen.
            self.setMinimumHeight(target_h)
            # The Handsome Handshake - We resize to the current width but the new target height
            self.resize(self.width(), target_h)
                
        else:
            # 5. Return back to doing all the fancy things it does and is famous for following a brief moment curled into its comfort security blanket
            target_h = self.old_height
            end_geo = QRect(start_geo.x(), start_geo.y(), start_geo.width(), target_h)

            # 6. This ensures the window has visual "weight" as it uncurls, and is correct order of operations, they both central and bottom start at the same time but central deliberately takes its time to get there later
            self.curtain_group.finished.connect(lambda: self.central.show())
            if hasattr(self, 'bottomToolbar'):
                self.bottomToolbar.show()

            # 7. Qt's default 'infinity' range
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            
            # 8. The Handsome Handshake - We resize it back to its original size once its done with the spectacle
            if hasattr(self, 'old_geometry'):
                self.setGeometry(start_geo)
            self.central.show()
        

        # 9. The Window Geometry Animation
        anim_geo = QPropertyAnimation(self, b"geometry")
        anim_geo.setDuration(pace)
        
        # THE CALIBRATION: 
        # If we are collapsing, we MUST force the start value to be the big height
        # even though we just called resize(). This tricks the animation 
        # into 're-expanding' the frame and then swooshing it down.
        if self.is_collapsed:
            anim_geo.setStartValue(self.old_geometry) 
        else:
            anim_geo.setStartValue(start_geo)
            
        anim_geo.setEndValue(end_geo)
        anim_geo.setEasingCurve(QEasingCurve.OutCubic)

        # 10. The Constraint Animation
        anim_max = QPropertyAnimation(self, b"maximumHeight")
        anim_max.setDuration(pace)
        
        # SAME CALIBRATION: Ensure the ceiling starts HIGH so it can glide LOW
        if self.is_collapsed:
            anim_max.setStartValue(self.old_height)
        else:
            anim_max.setStartValue(self.height())
            
        anim_max.setEndValue(target_h)
        anim_max.setEasingCurve(QEasingCurve.OutCubic)

        # 12. Execute and Rejoice
        self.curtain_group.addAnimation(anim_geo)
        self.curtain_group.addAnimation(anim_max)
        # self.curtain_group.addAnimation(anim_min)
        self.curtain_group.start()
        self.updateGeometry()


    def _setupBottomToolbar(self):
        self.bottomToolbar = QWidget()
        self.bottomToolbar.setFixedHeight(Theme.handleHeightBottom)

        layout = QHBoxLayout(self.bottomToolbar)
        layout.setContentsMargins(*Theme.layoutMargins)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)

    def setup_iconic_button(self, clicked=None, icon: str | None = None) -> QPushButton:
            """Creates a square icon-only button. icon= filename via Theme.icon()."""
            btn = button("", icon=QIcon(Theme.icon(Theme.iconPathCurtains)))
            btn.setFixedSize(QSize(Theme.iconButtonSize, Theme.iconButtonSize))
            btn.setIconSize(QSize(
                Theme.iconButtonSize - Theme.iconPadding,
                Theme.iconButtonSize - Theme.iconPadding
            ))
            btn.setStyleSheet(btn.styleSheet())
            if clicked is not None:
                btn.clicked.connect(clicked)
            return btn

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < Theme.handleHeightTop:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None