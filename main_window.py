#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main_window.py main application window
-One day it woke up and dreamt of becoming a frameless window with draggable toolbars and a node graphics view for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QComboBox, QGraphicsScene, QGraphicsView, QSplitter, QSizePolicy, QSlider, QProgressBar
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QSize, QRect
from graphics.Scene import IntricateScene
from graphics.View import IntricateView
from graphics.Theme import Theme
from widgets.PrettyButton import button


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

    def setup_iconic_button(self, clicked=None, icon: str | None = None) -> QPushButton:
            """Creates a square icon-only button. icon= filename string via Theme.icon()."""
            icon_name = icon if icon is not None else Theme.iconCurtains
            btn = button("", icon_name=icon_name)
            btn.setFixedSize(QSize(Theme.iconButtonSize, Theme.iconButtonSize))
            btn.setIconSize(QSize(
                Theme.iconButtonSize - Theme.iconPadding,
                Theme.iconButtonSize - Theme.iconPadding
            ))
            btn.setStyleSheet(btn.styleSheet())
            if clicked is not None:
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


    # =================================================================================
    # The central area — sidebar | canvas | reserved for a special vip arriving later
    # =================================================================================

    def _setupTheAreaFormerlyKnownAsNodal(self):
        """
        The central shelf — three zones in a horizontal QSplitter:

            Left  — NodeSidebar: icon buttons for node creation
            Center — IntricateView: the infinite canvas
            Right  — Reserved: the VIP arrives later (page renderer)

        QSplitter gives us the harmonica — drag the divider to collapse
        or expand any zone. The right zone starts at zero width until needed.
        """
        self.central = QWidget()
        self.scene   = IntricateScene()
        self.view    = IntricateView(self.scene)

        # ── Left sidebar ──────────────────────────────────────────────────────
        self.sidebar_layout = QHBoxLayout(self.central)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()

        # ── Right reserved ────────────────────────────────────────────────────
        # Empty widget — holds the slot open in the splitter for the VIP.
        self.rightReserved = QWidget()
        self.rightReserved.setFixedWidth(0)   # Collapsed until needed
        self.rightReserved.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Expanding
        )

        # ── Splitter ──────────────────────────────────────────────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Theme.primaryBorder};
            }}
        """)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.rightReserved)

        # Canvas takes all available slack — sidebar and right zone are fixed
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        
        self.sidebar_layout.addWidget(self.splitter)

        self.grid.addWidget(self.central, 1, 0)

    # =================================================================================
    # The actual sidebar
    # =================================================================================

    def _build_sidebar(self) -> QWidget:
        """
        Build the node creation sidebar.

        Icon-only buttons grouped by category. Width derives entirely from
        Theme.sidebarWidth() so it stays in sync with iconButtonSize.

        Categories:
            Canvas     — WarmNode, AboutNode, BezierNode
            Diagnostic — HealthNode (one per scene, button reflects this)
        """

        sidebar = QWidget()
        sidebar.setFixedWidth(Theme.sidebarWidth())
        sidebar.setStyleSheet(f"background-color: {Theme.windowBg};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(
            Theme.sidebarPadding, Theme.sidebarPadding,
            Theme.sidebarPadding, Theme.sidebarPadding
        )
        layout.setSpacing(Theme.sidebarButtonGap)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        tools = [
            (Theme.iconAbout, self._spawn_about_node, "Sticky note"),
            (Theme.iconWarm, self._spawn_warm_node, "Warm and Comfortable Writing Node"),
            (Theme.iconImage, self._spawn_image_node, "The Glorious Image Node"),
            (Theme.iconBezier, self._spawn_bezier_node, "The Prestigious Bezier Node"),
            (Theme.iconHealth, self._spawn_health_node, "The Oddly Important Health Node"),

        ]

        for icon, slot, description in tools:
            btn = button(icon_name=icon, clicked=slot,tooltip=description)
            btn.setFixedSize(Theme.iconButtonSize, Theme.iconButtonSize)
            layout.addWidget(btn)

        # ── Stretch pushes slider/bar to the bottom ───────────────────────────
        layout.addStretch()

        # ── Fog slider ────────────────────────────────────────────────────────
        # Vertical, top = opaque (255), bottom = transparent (0).
        # Placeholder — will drive fog layer alpha when that arrives.
        self.fog_slider = QSlider(Qt.Vertical)
        self.fog_slider.setRange(0, 255)
        self.fog_slider.setValue(180)
        self.fog_slider.setInvertedAppearance(True)
        self.fog_slider.setFixedWidth(Theme.sidebarWidth() - Theme.sidebarPadding * 2)
        self.fog_slider.setMinimumHeight(80)
        self.fog_slider.setStyleSheet(f"""
            QSlider::groove:vertical {{
                background: {Theme.primaryBorder};
                width: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:vertical {{
                background: {Theme.textPrimary};
                width: 12px; height: 12px;
                margin: 0 -4px;
                border-radius: 6px;
            }}
            QSlider::sub-page:vertical {{
                background: {Theme.backDrop};
                border-radius: 2px;
            }}
        """)
        self.fog_slider.valueChanged.connect(self._on_fog_slider_changed)
        layout.addWidget(self.fog_slider, alignment=Qt.AlignHCenter)

        layout.addSpacing(4)

        # ── Progress bar ──────────────────────────────────────────────────────
        # Vertical, fills bottom-to-top mirroring the slider.
        # Connected to fog_slider for functional testing.
        self.fog_progress = QProgressBar()
        self.fog_progress.setOrientation(Qt.Vertical)
        self.fog_progress.setRange(0, 255)
        self.fog_progress.setValue(180)
        self.fog_progress.setTextVisible(False)
        self.fog_progress.setFixedWidth(Theme.sidebarWidth() - Theme.sidebarPadding * 2)
        self.fog_progress.setMinimumHeight(60)
        self.fog_progress.setStyleSheet(f"""
            QProgressBar {{
                background: {Theme.backDrop};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {Theme.primaryBorder};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.fog_progress, alignment=Qt.AlignHCenter)
        layout.addSpacing(Theme.sidebarPadding)

        return sidebar

    def _on_fog_slider_changed(self, value: int) -> None:
        """Slider → progress bar mirror. Will drive fog alpha when fog arrives."""
        self.fog_progress.setValue(value)

    # def _sidebar_button(self, icon: str, tooltip: str, clicked) -> QPushButton:
    #     """Square icon-only sidebar button via setup_iconic_button."""
    #     btn = self.setup_iconic_button(clicked=clicked, icon=icon)
    #     btn.setToolTip(tooltip)
    #     return btn

    # ─────────────────────────────────────────────────────────────────────────
    # NODE SPAWN ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _viewport_center(self):
        """Current viewport center in scene coordinates."""
        vp = self.view.viewport()
        return self.view.mapToScene(vp.width() // 2, vp.height() // 2)

    def _spawn_warm_node(self):
        self.scene.add_warm_node(pos=self._viewport_center())

    def _spawn_about_node(self):
        self.scene.add_about_node(pos=self._viewport_center())

    def _spawn_bezier_node(self):
        self.scene.add_bezier_node(pos=self._viewport_center())

    def _spawn_health_node(self):
        self.scene.add_health_node(pos=self._viewport_center())

    def _spawn_image_node(self):
        self.scene.add_image_node(pos=self._viewport_center())



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
        layout.addWidget(button("Demo", clicked=self._open_demo_dialog))
        layout.addWidget(button("Settings", clicked=self._open_settings_dialog))
        layout.addWidget(button("Exid", clicked=self.close))   # Note: "Exid" is not a typo, its an Exit button named Exid

        self.grid.addWidget(self.bottomToolbar, 2, 0)

    def _open_settings_dialog(self):
        # Because it's a QWidget now, we need to ensure it doesn't get garbage collected
        if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(self)
        
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _open_demo_dialog(self):

        dlg = DemoDialog(self)
        dlg.show()

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

    def _cleanup_pycache(self) -> None:
        """
        Remove all __pycache__ folders and .pyc files under the project root.
        Equivalent to the 'housekeeping' PowerShell alias.
        Always runs fresh on next launch — no stale bytecode, no surprises.
        Non-fatal: if cleanup fails for any reason the app still exits cleanly.
        """
        import shutil
        from pathlib import Path
        root = Path(__file__).resolve().parent
        cleaned = 0
        try:
            for item in root.rglob("__pycache__"):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned += 1
            for item in root.rglob("*.pyc"):
                item.unlink(missing_ok=True)
            print(f"Python cache cleaned! ({cleaned} __pycache__ folders removed) ✨")
        except Exception as e:
            print(f"Cache cleanup skipped: {e}")

    def closeEvent(self, event):
        """
        It should be a joyful moment because now we can look forward to seeing each other later.
        """
        if self.windowOpacity() <= 0.0:
            self._cleanup_pycache()
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
