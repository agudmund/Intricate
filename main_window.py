#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main_window.py main application window
-One day it woke up and dreamt of becoming a frameless window with draggable toolbars and a node graphics view for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QGraphicsScene, QGraphicsView, QSplitter, QSizePolicy, QSlider, QProgressBar, QLabel, QFrame, QScrollArea
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QSize, QRect, QEvent, QTimer
from graphics.Scene import IntricateScene
from graphics.View import IntricateView
from graphics.Theme import Theme
from widgets.PrettyButton import button
from utils.logger import setup_logger
from utils.settings import appName, set_nested, set_value, get
from widgets.PrettyCombo import combo as pretty_combo
from widgets.PrettyLabel import label as pretty_label

logger = setup_logger()


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
        self._is_fullscreen = False

        # 3.  Window OS Defaults
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # self.setAttribute(Qt.WA_TranslucentBackground) # this is for the selective blur later
        self.setMinimumSize(500, 500)
        
        # 4. Grid and widget setup
        self._setup_grid()
        self._build_top_toolbar()
        self._setupTheAreaFormerlyKnownAsNodal()
        self._setupBottomToolbar()

        # 5. Restore persisted geometry
        self._restore_geometry()

        # 6. Load session for the initially selected project, then start autosave
        QTimer.singleShot(0, self._load_initial_session)

    def _setup_grid(self):
        """
        3-row grid — the permanent skeleton of the window.

        Row 0: top_toolbar   — fixed height, anchored to top
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

    def _build_top_toolbar(self):
        """
        Row 0 — top toolbar shelf.
        Fixed height. Drag-to-move via mouse events below.

        Layout:  [ stretch | centered title | curtains btn | stretch ]
                 [ exit btn — absolute, pinned to top-right corner    ]

        Button sizes are derived from QFontMetrics on the label font so they
        scale automatically if the font size or toolbar height ever changes.
        The exit button is an absolute child of top_toolbar; resizeEvent keeps
        it anchored to the right edge as the window width changes.
        """
        self.top_toolbar = QWidget()
        self.top_toolbar.setFixedHeight(Theme.handleHeightTop)
        self.top_toolbar.setStyleSheet(f"background-color: {Theme.windowBg};")

        layout = QHBoxLayout(self.top_toolbar)
        layout.setContentsMargins(*Theme.layoutMargins)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignVCenter)

        # Stretch pushes combo to center
        layout.addStretch()

        # Centered project selector — acts as the window title
        layout.addWidget(self.setup_project_selector(), alignment=Qt.AlignVCenter)

        layout.addSpacing(6)

        # Curtains button — sits right of the combo
        layout.addWidget(self.setup_iconic_button(clicked=self.toggle_curtains))

        # Stretch balances right side
        layout.addStretch()

        # ── Exit button: absolute child of top_toolbar, pinned to top-right ──────
        # Icon-only square button — size matches the other toolbar icon buttons.
        self._exit_btn = self.setup_iconic_button(
            clicked=self.close, icon=Theme.iconClose
        )
        self._exit_btn.setParent(self.top_toolbar)
        # Deferred first position — toolbar width isn't known at construction time
        QTimer.singleShot(0, self._reposition_exit_btn)

        self.grid.addWidget(self.top_toolbar, 0, 0)
        self.top_toolbar.installEventFilter(self)

    def _reposition_exit_btn(self) -> None:
        """Keep the exit button pinned to the top-right corner of the toolbar."""
        if not hasattr(self, '_exit_btn') or not hasattr(self, 'top_toolbar'):
            return
        btn = self._exit_btn
        tb  = self.top_toolbar
        btn.move(tb.width() - btn.width() - 4,
                 (tb.height() - btn.height()) // 2)
        btn.raise_()

    def setup_project_selector(self):
        """The Project Selector Combo Box"""

        # Make sure that the sessions are populated before connecting the signal otherwise the literal seventh level of hades arrives needing over 200 lines of code to account for disabling and enabling the session list
        self.project_selector = pretty_combo()
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
    # Fullscreen toggle — double-click the top toolbar
    # =========================================================================

    def eventFilter(self, obj, event):
        if obj is self.top_toolbar and event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                self.toggle_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            if hasattr(self, '_pre_fullscreen_geometry'):
                self.setGeometry(self._pre_fullscreen_geometry)
        else:
            self._pre_fullscreen_geometry = self.geometry()
            self.showFullScreen()
        self._is_fullscreen = not self._is_fullscreen

    # =========================================================================
    # Curtains, The Window Rollup Thing
    # =========================================================================

    def toggle_curtains(self):
        """Animate the window into a sleek HUD strip."""
        self.setMinimumHeight(0)
        start_rect = self.geometry()

        if not self.is_collapsed:
            self.original_height = self.height()
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), Theme.handleHeightTop)
            self.central.hide()
            self.bottomToolbar.hide()
        else:
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), self.original_height)
            self.central.show()
            self.bottomToolbar.show()

        self._animate_curtains(start_rect, end_rect)
        self.is_collapsed = not self.is_collapsed

    def _animate_curtains(self, start_rect: QRect, end_rect: QRect) -> None:
        """Drive the geometry animation for curtain collapse / expand."""
        self.curtain_anim = QPropertyAnimation(self, b"geometry")
        self.curtain_anim.setDuration(450)
        self.curtain_anim.setEasingCurve(QEasingCurve.OutExpo)
        self.curtain_anim.setStartValue(start_rect)
        self.curtain_anim.setEndValue(end_rect)
        self.curtain_anim.start()


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
        self.view._on_zoom_changed = lambda: self._sync_zoom_slider()

        # ── Left sidebar ──────────────────────────────────────────────────────
        self.sidebar_layout = QHBoxLayout(self.central)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()

        # ── Right panel — image preview zone ──────────────────────────────────
        self.rightPanel = self._build_preview_panel()

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
        self.splitter.addWidget(self.rightPanel)

        # Canvas takes all slack; sidebar and preview zone follow their own minimums
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        # Allow the right panel to collapse fully to zero width when dragged shut
        self.splitter.setCollapsible(2, True)

        # Restore saved preview panel width, default to 0 (collapsed)
        QTimer.singleShot(0, self._restore_preview_width)

        
        self.sidebar_layout.addWidget(self.splitter)

        self.grid.addWidget(self.central, 1, 0)

    # =================================================================================
    # Right panel — image preview
    # =================================================================================

    def _build_preview_panel(self) -> QFrame:
        """
        Right splitter zone — shows a scaled preview of the selected ImageNode.

        Layout:
            ┌──────────────────────┐
            │  caption label       │
            │  ┌────────────────┐  │
            │  │                │  │
            │  │   QLabel img   │  │
            │  │  (scaled fit)  │  │
            │  │                │  │
            │  └────────────────┘  │
            │  dim label           │
            └──────────────────────┘

        Starts at zero width (collapsed). Drag the splitter handle to reveal it.
        """
        panel = QFrame()
        panel.setFrameShape(QFrame.NoFrame)
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        panel.setStyleSheet(f"background: {Theme.windowBg};")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # ── Top bar: caption + pin button ────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(4)

        self._preview_caption = QLabel("")
        self._preview_caption.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._preview_caption.setWordWrap(True)
        self._preview_caption.setMinimumWidth(0)
        self._preview_caption.setStyleSheet(f"""
            QLabel {{
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                padding: 2px 4px;
            }}
        """)
        top_bar.addWidget(self._preview_caption, stretch=1)

        self._pin_btn = QPushButton("○")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(False)
        self._pin_btn.setFixedSize(22, 22)
        self._pin_btn.setToolTip("Pin preview — keeps this image while you select other nodes")
        self._pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.primaryBorder};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 11px;
                font-size: 10pt;
                padding: 0;
            }}
            QPushButton:checked {{
                background: {Theme.primaryBorder};
                color: {Theme.windowBg};
            }}
            QPushButton:hover {{
                border-color: {Theme.textPrimary};
                color: {Theme.textPrimary};
            }}
        """)
        self._pin_btn.toggled.connect(self._on_pin_toggled)
        top_bar.addWidget(self._pin_btn)

        layout.addLayout(top_bar)

        # Image label — fills remaining space, scales the pixmap to fit
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._preview_label.setMinimumSize(0, 0)
        self._preview_label.setStyleSheet("background: transparent;")
        layout.addWidget(self._preview_label, stretch=1)

        # Dimensions hint
        self._preview_dims = QLabel("")
        self._preview_dims.setAlignment(Qt.AlignCenter)
        self._preview_dims.setMinimumWidth(0)
        self._preview_dims.setStyleSheet(f"""
            QLabel {{
                color: {Theme.primaryBorder};
                font-family: {Theme.healthFontFamily};
                font-size: 8pt;
            }}
        """)
        layout.addWidget(self._preview_dims)

        self._preview_pinned: bool = False
        self._preview_pixmap: QPixmap | None = None
        self._pinned_source_path: str = ""
        panel.resizeEvent = lambda e, orig=panel.resizeEvent: (orig(e), self._refresh_preview_scale())

        return panel

    def _restore_preview_width(self) -> None:
        """Restore saved splitter sizes (sidebar and preview panel widths persisted in settings)."""
        saved_preview = get("ui", "preview_width", 0)
        saved_sidebar = get("ui", "sidebar_width", 0)
        sizes = self.splitter.sizes()
        if len(sizes) == 3:
            new_sidebar  = saved_sidebar if saved_sidebar > 0 else sizes[0]
            new_preview  = saved_preview if saved_preview > 0 else sizes[2]
            slack        = sizes[0] + sizes[1] + sizes[2] - new_sidebar - new_preview
            self.splitter.setSizes([new_sidebar, max(0, slack), new_preview])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """Persist sidebar and preview panel widths whenever the splitter moves."""
        sizes = self.splitter.sizes()
        if len(sizes) == 3:
            set_value("ui", "sidebar_width", sizes[0])
            set_value("ui", "preview_width", sizes[2])

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._preview_pinned = pinned
        self._pin_btn.setText("●" if pinned else "○")
        if not pinned:
            # Re-evaluate immediately so deselecting clears stale preview
            self._on_selection_changed()
        if pinned and self._preview_pixmap:
            # Persist which image is pinned so it survives a restart
            set_value("ui", "preview_pinned", True)
            set_value("ui", "preview_pinned_path", self._pinned_source_path or "")
        else:
            set_value("ui", "preview_pinned", False)
            set_value("ui", "preview_pinned_path", "")

    def _update_preview(self, pixmap: QPixmap | None, caption: str = "", dims: str = "") -> None:
        """Push a new image into the preview panel."""
        self._preview_pixmap = pixmap
        self._preview_caption.setText(caption)
        self._preview_dims.setText(dims)
        self._refresh_preview_scale()

    def _refresh_preview_scale(self) -> None:
        """Re-scale the stored pixmap to the current label size (called on resize too)."""
        if not self._preview_pixmap or self._preview_pixmap.isNull():
            self._preview_label.clear()
            return
        size = self._preview_label.size()
        if size.width() < 2 or size.height() < 2:
            return
        scaled = self._preview_pixmap.scaled(
            size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._preview_label.setPixmap(scaled)

    def _on_selection_changed(self) -> None:
        """Update the preview panel when selection changes — skipped while pinned."""
        if self._preview_pinned:
            return
        from nodes.ImageNode import ImageNode
        selected = self.scene.selectedItems()
        for item in selected:
            if isinstance(item, ImageNode) and item._pixmap and not item._pixmap.isNull():
                px = item._pixmap
                caption = item.data.caption or item.data.title
                dims = f"{px.width()} × {px.height()}"
                self._pinned_source_path = item.data.source_path or ""
                self._update_preview(px, caption, dims)
                return
        self._pinned_source_path = ""
        self._update_preview(None)

    def _restore_pinned_preview(self) -> None:
        """After session load: re-pin the previously pinned image if still present."""
        if not get("ui", "preview_pinned", False):
            return
        saved_path = get("ui", "preview_pinned_path", "")
        if not saved_path:
            return
        from nodes.ImageNode import ImageNode
        for item in self.scene.items():
            if isinstance(item, ImageNode) and item._pixmap and not item._pixmap.isNull():
                if item.data.source_path == saved_path:
                    px = item._pixmap
                    caption = item.data.caption or item.data.title
                    dims = f"{px.width()} × {px.height()}"
                    self._pinned_source_path = saved_path
                    self._update_preview(px, caption, dims)
                    # Activate pin button without triggering _on_pin_toggled's save
                    self._preview_pinned = True
                    self._pin_btn.blockSignals(True)
                    self._pin_btn.setChecked(True)
                    self._pin_btn.setText("●")
                    self._pin_btn.blockSignals(False)
                    return

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
            (Theme.iconClaude, self._spawn_claude_node, "Claude Node"),
            (Theme.iconText,  self._spawn_text_node,   "Text Node"),
            (Theme.iconSequence, self._spawn_sequence_node, "Image Sequence Scrubber"),
            (Theme.iconTree,    self._spawn_tree_node,     "Folder Structure"),
            (Theme.iconHealth,  self._spawn_perf_node,     "Paint Performance Monitor"),
            (Theme.iconClaude,  self._spawn_claude_info_node, "Claude Token Census"),
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

    # ─────────────────────────────────────────────────────────────────────────
    # NODE SPAWN ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _viewport_center(self):
        """Current viewport center in scene coordinates."""
        vp = self.view.viewport()
        return self.view.mapToScene(vp.width() // 2, vp.height() // 2)

    def _spawn_warm_node(self):
        self.scene.add_warm_node(pos=self._viewport_center())
        self._status("a warm thought arrives")

    def _spawn_about_node(self):
        self.scene.add_about_node(pos=self._viewport_center())
        self._status("a little note for later")

    def _spawn_bezier_node(self):
        self.scene.add_bezier_node(pos=self._viewport_center())
        self._status("curves ahead")

    def _spawn_health_node(self):
        self.scene.add_health_node(pos=self._viewport_center())
        self._status("checking in on things")

    def _spawn_claude_node(self):
        self.scene.add_claude_node(pos=self._viewport_center())
        self._status("claude has entered the chat")

    def _spawn_image_node(self):
        self.scene.add_image_node(pos=self._viewport_center())
        self._status("a picture is worth everything")

    def _spawn_text_node(self):
        self.scene.add_text_node(pos=self._viewport_center())
        self._status("words, words, words")

    def _spawn_sequence_node(self):
        self.scene.add_sequence_node(pos=self._viewport_center())
        self._status("ready to scrub")

    def _spawn_tree_node(self):
        path = self._session_path()
        project_path = str(path.parent) if path else ""
        self.scene.add_tree_node(pos=self._viewport_center(), project_path=project_path)
        self._status("mapping the territory")

    def _spawn_perf_node(self):
        self.scene.add_perf_node(pos=self._viewport_center())
        self._status("watching the paint loop")

    def _spawn_claude_info_node(self):
        self.scene.add_claude_info_node(pos=self._viewport_center())
        self._status("counting every token with pride")

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

        # ── Selection info label — left side ─────────────────────────
        self._selection_label = pretty_label("")
        layout.addWidget(self._selection_label, alignment=Qt.AlignVCenter)

        layout.addStretch()

        # ── Zoom slider — horizontal, maps 0.1–5.0 to integer range ──────
        self._zoom_label = pretty_label("100%")
        self._zoom_label.setFixedWidth(42)
        layout.addWidget(self._zoom_label, alignment=Qt.AlignVCenter)

        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setFixedWidth(120)
        self._zoom_slider.setMinimum(10)    # 0.1× zoom × 100
        self._zoom_slider.setMaximum(500)   # 5.0× zoom × 100
        self._zoom_slider.setValue(100)
        self._zoom_slider.setSingleStep(5)
        self._zoom_slider.setPageStep(25)
        self._zoom_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 3px;
                background: {Theme.primaryBorder};
                border-radius: 1px;
            }}
            QSlider::handle:horizontal {{
                width: 10px;
                margin: -4px 0;
                background: {Theme.textPrimary};
                border-radius: 5px;
            }}
        """)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider)
        layout.addWidget(self._zoom_slider, alignment=Qt.AlignVCenter)

        # Exid button — lower-right anchor, styled via PrettyButton
        self._exid_btn = button("Exid", clicked=self.close)
        layout.addWidget(self._exid_btn, alignment=Qt.AlignVCenter)

        self.grid.addWidget(self.bottomToolbar, 2, 0)

    def _on_zoom_slider(self, value: int) -> None:
        """Slider dragged — set the view zoom to the slider's value."""
        target = value / 100.0
        current = self.view.current_zoom
        if abs(target - current) < 0.001:
            return
        factor = target / current
        self.view._apply_zoom(factor)
        self._zoom_label.setText(f"{value}%")

    def _sync_zoom_slider(self) -> None:
        """Called after wheel-zoom to keep the slider in sync with the view."""
        value = int(round(self.view.current_zoom * 100))
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(max(10, min(500, value)))
        self._zoom_slider.blockSignals(False)
        self._zoom_label.setText(f"{value}%")

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
    # Status Bar — warm, hospitable feedback on major UI moments
    # =========================================================================

    def _status(self, text: str) -> None:
        """Show a warm status message in the bottom toolbar."""
        self._selection_label.setText(text)

    # =========================================================================
    # Sessions
    # =========================================================================

    def _session_path(self, project: str | None = None) -> 'Path | None':
        """Return the session.json path for a project folder name."""
        from pathlib import Path
        name = project if project is not None else self.project_selector.currentText()
        if not name:
            return None
        return Path.home() / "Desktop" / name / "session.json"

    def _swap_scene(self) -> None:
        """Replace the current scene with a fresh one on the view.

        Avoids calling removeItem on live nodes — instead the old scene is
        handed to Python GC while the view gets a clean canvas immediately.
        The autosave signal is re-wired to the new scene.
        """
        old_scene = self.scene
        try:
            old_scene.changed.disconnect(self._schedule_autosave)
        except RuntimeError:
            pass

        # Sever Qt C++ signal connections on the old scene so its nodes
        # can be collected — without this, behaviour animations and glide
        # timers create C++-side reference cycles that Python's GC can't break.
        old_scene._release_all()

        self.scene = IntricateScene()
        self.view.setScene(self.scene)
        self.scene.changed.connect(self._schedule_autosave)
        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _autosave(self) -> None:
        """Save the current canvas to the active project's session.json."""
        path = self._session_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.scene.save_session(path)

    def _schedule_autosave(self) -> None:
        """Debounce scene changes — save 2 s after the last modification."""
        self._autosave_timer.start(2000)

    def _init_autosave(self) -> None:
        """Create the debounce timer and wire scene signals."""
        self._autosave_timer = QTimer()
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave)
        self.scene.changed.connect(self._schedule_autosave)
        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _load_initial_session(self) -> None:
        """Load the session for the startup-selected project and wire autosave."""
        import os
        self._init_autosave()
        path = self._session_path()
        if path and path.parent.exists():
            try:
                os.chdir(str(path.parent))
            except OSError:
                pass
        if path:
            if path.exists():
                self.scene.load_session(path)
            self.scene.sync_project_images(path.parent)
        QTimer.singleShot(0, self._restore_camera)
        QTimer.singleShot(0, self._restore_pinned_preview)

    def on_session_changed(self) -> None:
        """Save the outgoing session, swap to a fresh scene, load incoming."""
        import utils.settings as _s
        new_project = self.project_selector.currentText()

        # Save whatever was on canvas for the previous project
        if hasattr(self, '_active_project'):
            prev_path = self._session_path(self._active_project)
            if prev_path:
                prev_path.parent.mkdir(parents=True, exist_ok=True)
                self.scene.save_session(prev_path)

        self._active_project = new_project
        _s.set_value("ui", "selected_project", new_project)

        # Change working directory to the new project folder
        import os
        from pathlib import Path
        new_project_dir = Path.home() / "Desktop" / new_project
        if new_project_dir.exists():
            try:
                os.chdir(str(new_project_dir))
            except OSError:
                pass

        # Fresh scene — avoids re-entrant Qt teardown on live nodes
        self._swap_scene()

        # Restore session then sync any new images from ./Images/ on disk
        path = self._session_path(new_project)
        if path:
            if path.exists():
                self.scene.load_session(path)
            self.scene.sync_project_images(path.parent)
        self._status(f"welcome back to {new_project}")

    def populate_sessions(self) -> None:
        import utils.settings as _s
        from pathlib import Path
        desktop = Path.home() / "Desktop"
        desktop_folders = sorted(
            p.name for p in desktop.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ) if desktop.exists() else []
        self.project_selector.addItems(desktop_folders)
        saved = _s.get("ui", "selected_project", "")
        if saved in desktop_folders:
            self.project_selector.setCurrentText(saved)
        self._active_project = self.project_selector.currentText()

    # =========================================================================
    # Mouse and Hover Events
    # =========================================================================

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_exit_btn()

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
        self._animate_fade_in()
        QTimer.singleShot(600, self._check_vaporize_restart)

    def _animate_fade_in(self) -> None:
        """Fade the window opacity from 0 → 1 on show."""
        self.fadeIn = QPropertyAnimation(self, b"windowOpacity")
        self.fadeIn.setDuration(500)
        self.fadeIn.setStartValue(0.0)
        self.fadeIn.setEndValue(1.0)
        self.fadeIn.setEasingCurve(QEasingCurve.OutCubic)
        self.fadeIn.start()

    def _check_vaporize_restart(self):
        """Spawn a response node if the previous session ended via 'then vaporize'."""
        import json
        from pathlib import Path
        flag = Path(__file__).resolve().parent / ".vaporize_restart.json"
        if not flag.exists():
            return
        try:
            data  = json.loads(flag.read_text(encoding="utf-8"))
            reply = data.get("reply", "").strip()
        except Exception:
            reply = ""
        flag.unlink(missing_ok=True)
        if reply:
            pos  = self._viewport_center()
            self.scene.add_claude_response_node(pos=pos, label=reply)

    def _restore_camera(self) -> None:
        """Restore the saved viewport centre and zoom level.

        Must run after session load.  Expands the scene rect to cover all loaded
        nodes first so centerOn has the full canvas to work with — otherwise the
        default (-500,-500,1000,1000) rect clamps the camera position.
        """
        cx   = get("window", "camera_x",    None)
        cy   = get("window", "camera_y",    None)
        zoom = get("window", "camera_zoom", None)
        if cx is None or cy is None:
            return
        # Expand scene to encompass all loaded nodes before positioning the camera
        self.view._expand_scene_rect()
        if zoom is not None and zoom > 0:
            self.view.resetTransform()
            self.view.scale(zoom, zoom)
            self.view.current_zoom = zoom
        from PySide6.QtCore import QPointF
        self.view.centerOn(QPointF(cx, cy))
        self._sync_zoom_slider()

    def _restore_geometry(self) -> None:
        x  = get("window", "x",      100)
        y  = get("window", "y",      100)
        w  = get("window", "width",  900)
        h  = get("window", "height", 700)
        self.setGeometry(x, y, w, h)
        if get("window", "fullscreen", False):
            self._is_fullscreen = True
            self.showFullScreen()

    def _save_geometry(self) -> None:
        if self._is_fullscreen and hasattr(self, '_pre_fullscreen_geometry'):
            r = self._pre_fullscreen_geometry
        else:
            r = self.geometry()
        set_value("window", "x",          r.x())
        set_value("window", "y",          r.y())
        set_value("window", "width",      r.width())
        set_value("window", "height",     r.height())
        set_value("window", "fullscreen", self._is_fullscreen)
        # Persist camera so the view reopens exactly where it was left
        try:
            vp_center = self.view.mapToScene(self.view.viewport().rect().center())
            set_value("window", "camera_x",    vp_center.x())
            set_value("window", "camera_y",    vp_center.y())
            set_value("window", "camera_zoom", self.view.current_zoom)
        except (RuntimeError, AttributeError):
            pass

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
        except Exception:
            pass

    def _persist_claude_node_size(self) -> None:
        from nodes.ClaudeNode import ClaudeNode
        nodes = [n for n in self.scene.items() if isinstance(n, ClaudeNode)]
        if nodes:
            node = nodes[-1]
            w = max(200.0, min(800.0, node.rect().width()))
            h = max(250.0, min(700.0, node.rect().height()))
            set_nested("node", "claude", "default_width",  w)
            set_nested("node", "claude", "default_height", h)

    def _run_exit_script(self) -> None:
        import subprocess
        import random
        import sys
        from pathlib import Path
        from utils.motivationalMessages import motivationalMessages
        word = random.choice(motivationalMessages)
        result = subprocess.run(
            f"@echo off & echo {word}",
            capture_output=True,
            text=True,
            shell=True,
        )
        if result.stdout.strip():
            logger.info(result.stdout.strip())
        import sys as _sys
        _main_module = _sys.modules.get('__main__')
        if _main_module is not None and getattr(_main_module, '_instance_lock', None) is not None:
            try:
                _main_module._instance_lock.close()
            except OSError:
                pass
            _main_module._instance_lock = None
        main = Path(__file__).resolve().parent / "main.py"
        subprocess.Popen(
            [sys.executable, str(main)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def closeEvent(self, event):
        """
        It should be a joyful moment because now we can look forward to seeing each other later.
        """
        if self.windowOpacity() <= 0.0:
            try:
                self._cleanup_pycache()
                self._persist_claude_node_size()
            except (RuntimeError, Exception):
                pass
            event.accept()
            return

        try:
            self._autosave()
        except (RuntimeError, Exception):
            pass
        try:
            self._save_geometry()
        except (RuntimeError, Exception):
            pass
        self._run_exit_script()
        event.ignore()
        self._animate_fade_out()
        logger.info(f"Exid: {appName} will be back as soon as we can! ✨")

    def _animate_fade_out(self) -> None:
        """Fade the window opacity from current → 0 and trigger close on finish."""
        self.fadeOut = QPropertyAnimation(self, b"windowOpacity")
        self.fadeOut.setDuration(300)
        self.fadeOut.setStartValue(self.windowOpacity())
        self.fadeOut.setEndValue(0.0)
        self.fadeOut.setEasingCurve(QEasingCurve.InCubic)
        self.fadeOut.finished.connect(self.close)
        self.fadeOut.start()
