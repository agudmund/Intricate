#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main_window.py main application window
-One day it woke up and dreamt of becoming a frameless window with draggable toolbars and a node graphics view for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import random

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QGraphicsScene, QGraphicsView, QSplitter, QSizePolicy, QSlider, QProgressBar, QLabel, QFrame, QScrollArea, QGraphicsOpacityEffect
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QPointF, QSize, QRect, QEvent, QTimer
from graphics.Scene import IntricateScene
from graphics.View import IntricateView
from graphics.Theme import Theme
from nodes.ClaudeNode import ClaudeNode
from nodes.ImageNode import ImageNode
from widgets.PrettyButton import button
from widgets.PrettyMenu import menu as pretty_menu
from utils.logger import setup_logger
from utils.PhrasePicker import motivationalMessages
from utils.settings import appName, set_nested, get_nested, set_value, get
from utils.helpers import ensure_dir, clean_pycache
from utils.session import session_path, enter_project
from widgets.PrettyCombo import combo as pretty_combo
from widgets.PrettyLabel import label as pretty_label
from widgets.PrettySlider import slider as pretty_slider

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
        self._shown_once = False

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
        layout.setContentsMargins(0, 2, 0, 2)
        # layout.setSpacing(20)

        layout.addStretch()

        # ── Centre group: combo + curtains in a tight sub-layout
        #    so they share a single vertical axis regardless of Qt's
        #    per-widget alignment quirks.
        centre = QHBoxLayout()
        # centre.setContentsMargins(0, 0, 0, 0)
        # centre.setSpacing(6)
        centre.setAlignment(Qt.AlignVCenter)
        centre.setSpacing(4)
        combo = self.setup_project_selector()
        centre.addWidget(combo)
        # Size the curtains button to match the combo height so they sit flush
        combo_h = combo.maximumHeight() or combo.sizeHint().height()
        self._curtains_btn = self.setup_iconic_button(
            clicked=self.toggle_curtains,
        )
        self._curtains_btn.setFixedSize(combo_h, combo_h)
        self._curtains_btn.setIconSize(QSize(combo_h - Theme.iconPadding,
                                             combo_h - Theme.iconPadding))
        centre.addWidget(self._curtains_btn)
        layout.addLayout(centre)

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

    def setup_iconic_button(self, clicked=None, icon: str | None = None,
                            margin_top: int = 0, margin_bottom: int = 0) -> QPushButton:
        """Creates a square icon-only button. icon= filename string via Theme.icon()."""
        icon_name = icon if icon is not None else Theme.iconCurtains
        btn = button("", icon_name=icon_name)
        sz = Theme.iconButtonSize
        btn.setFixedSize(QSize(sz, sz))
        btn.setIconSize(QSize(sz - Theme.iconPadding, sz - Theme.iconPadding))
        bw = Theme.buttonBorderWidth if Theme.buttonBorderEnabled else 0
        margins = ""
        if margin_top:    margins += f"margin-top: {margin_top}px; "
        if margin_bottom: margins += f"margin-bottom: {margin_bottom}px; "
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.buttonBg};
                border: {bw}px solid {Theme.buttonBorder};
                border-radius: 6px;
                color: {Theme.textPrimary};
                padding: 0px;
                {margins}
            }}
        """)
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
        fw = self.focusWidget()
        if fw:
            fw.clearFocus()
        self.setMinimumHeight(0)
        start_rect = self.geometry()

        if not self.is_collapsed:
            self.original_height = self.height()
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), Theme.handleHeightTop)
            self.central.hide()
            self.bottomToolbar.hide()
            # Pause all videos — curtains hide the canvas
            if self.scene:
                self.scene.pause_all_videos()
        else:
            end_rect = QRect(start_rect.x(), start_rect.y(), start_rect.width(), self.original_height)
            self.central.show()
            self.bottomToolbar.show()

        self._animate_curtains(start_rect, end_rect)
        self.is_collapsed = not self.is_collapsed

    def _animate_curtains(self, start_rect: QRect, end_rect: QRect) -> None:
        """Drive the geometry animation for curtain collapse / expand."""
        self.view.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.curtain_anim = QPropertyAnimation(self, b"geometry")
        self.curtain_anim.setDuration(Theme.windowRollTiming)
        self.curtain_anim.setEasingCurve(
            getattr(QEasingCurve, Theme.windowRollEasing, QEasingCurve.OutExpo)
        )
        self.curtain_anim.setStartValue(start_rect)
        self.curtain_anim.setEndValue(end_rect)
        self.curtain_anim.finished.connect(self._on_curtains_settled)
        self.curtain_anim.start()

    def _on_curtains_settled(self) -> None:
        """Called when the curtains animation finishes (both collapse and restore).

        The view is configured with NoAnchor and must stay that way — AnchorViewCenter
        causes Qt to call centerOn() after every translate(), which cancels every pan
        stroke and makes the canvas appear frozen. Scrub any stale grabber too.
        """
        # NoAnchor is the view's native state (set in _configure). Restoring
        # AnchorViewCenter here was the root cause of pan being dead after curtains.
        self.view.setTransformationAnchor(QGraphicsView.NoAnchor)
        scene = self.scene
        if scene:
            grabber = scene.mouseGrabberItem()
            if grabber:
                grabber.ungrabMouse()
        # Reset pan state — a stale non-None _last_pan_pos after a
        # visibility change would lock the view into phantom-pan mode.
        self.view._last_pan_pos = None
        # Re-evaluate video visibility after curtains expand
        if not self.is_collapsed:
            self.view._notify_viewport_changed()


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
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: transparent;
            }
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
        panel.setStyleSheet("background: transparent;")

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
        saved_preview = get("ui", "preview_width", None)
        saved_sidebar = get("ui", "sidebar_width", 0)
        sizes = self.splitter.sizes()
        if len(sizes) == 3:
            new_sidebar  = saved_sidebar if saved_sidebar > 0 else sizes[0]
            new_preview  = saved_preview if saved_preview is not None else sizes[2]
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

    def _show_node_preview(self, node: ImageNode) -> None:
        """Push one ImageNode's pixmap into the preview panel."""
        px = node._pixmap
        self._pinned_source_path = node.data.source_path or ""
        self._update_preview(
            px,
            node.data.caption or node.data.title,
            f"{px.width()} × {px.height()}",
        )

    def _on_selection_changed(self) -> None:
        """Update the preview panel when selection changes — skipped while pinned."""
        if self._preview_pinned:
            return
        for item in self.scene.selectedItems():
            if isinstance(item, ImageNode) and item._pixmap and not item._pixmap.isNull():
                self._show_node_preview(item)
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
        for item in self.scene.items():
            if isinstance(item, ImageNode) and item._pixmap and not item._pixmap.isNull():
                if item.data.source_path == saved_path:
                    self._show_node_preview(item)
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
        sidebar.setStyleSheet("background-color: transparent;")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(
            Theme.sidebarPadding, Theme.sidebarPadding,
            Theme.sidebarPadding, Theme.sidebarPadding
        )
        layout.setSpacing(Theme.sidebarButtonGap)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        def _cat_btn(icon_name, tooltip, menu_fn):
            """Category button — icon fills the entire button, no Qt frame overhead."""
            sz = Theme.iconButtonSize
            b = button(icon_name=icon_name, tooltip=tooltip)
            b.setFixedSize(sz, sz)
            b.setIconSize(QSize(sz, sz))
            b.setFlat(True)
            b.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")
            b.clicked.connect(lambda _=None, btn=b: menu_fn(btn))
            layout.addWidget(b)

        _cat_btn(Theme.iconText,        "Text",   self._show_text_menu)
        _cat_btn(Theme.iconImagesGroup,  "Images", self._show_images_menu)
        _cat_btn(Theme.iconVisualGroup,  "Visual", self._show_visual_menu)
        _cat_btn(Theme.iconHealthGroup,  "Health", self._show_health_menu)
        _cat_btn(Theme.iconToolsGroup,   "Tools",  self._show_tools_menu)
        _cat_btn(Theme.iconClaude,       "Claude", self._show_claude_menu)

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

    def _spawn(self, add_fn, status_msg: str, **kwargs) -> None:
        """Place a node at the viewport centre and update the status bar."""
        try:
            add_fn(pos=self._viewport_center(), **kwargs)
        except Exception:
            logger.exception("Failed to spawn node via %s", add_fn.__name__)
            return
        self._status(status_msg)

    def _spawn_warm_node(self):        self._spawn(self.scene.add_warm_node,         "a warm thought arrives")
    def _spawn_about_node(self):       self._spawn(self.scene.add_about_node,        "a little note for later")
    def _spawn_bezier_node(self):      self._spawn(self.scene.add_bezier_node,       "curves ahead")
    def _spawn_health_node(self):      self._spawn(self.scene.add_health_node,       "checking in on things")
    def _spawn_claude_node(self):      self._spawn(self.scene.add_claude_node,       "claude has entered the chat")
    def _spawn_image_node(self):       self._spawn(self.scene.add_image_node,        "a picture is worth everything")
    def _spawn_video_node(self):       self._spawn(self.scene.add_video_node,        "lights, camera, action")
    def _spawn_text_node(self):        self._spawn(self.scene.add_text_node,         "words, words, words")
    def _spawn_log_node(self):         self._spawn(self.scene.add_log_node,          "tailing the log")

    def _spawn_readme_node(self) -> None:
        """Spawn a text node pre-filled with README.md from the session project root."""
        path = self._session_path()
        if not path:
            return
        readme = path.parent / "README.md"
        if not readme.exists():
            self._status("no README.md found in project root")
            return
        try:
            text = readme.read_text(encoding="utf-8")
        except Exception:
            self._status("could not read README.md")
            return
        self._spawn(self.scene.add_text_node, "the README has arrived", label=text)
    def _spawn_sequence_node(self):    self._spawn(self.scene.add_sequence_node,     "ready to scrub")
    def _spawn_value_node(self):       self._spawn(self.scene.add_value_node,        "dialing in the value")
    def _spawn_palette_node(self):     self._spawn(self.scene.add_palette_node,      "mixing colors")

    def _restore_deleted(self) -> None:
        if self.scene.restore_last_deleted():
            self._status("restored from the ashes")
        else:
            self._status("nothing to restore")

    def _start_wire_snip(self) -> None:
        self.view.start_snip_mode()
        self._status("click a wire to snip it")

    def _styled_menu(self):
        """Create a PrettyMenu styled to match the app's visual language."""
        return pretty_menu(self)
        return menu

    def _show_text_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the text group button."""
        menu = self._styled_menu()
        act_about = menu.addAction(QIcon(Theme.icon(Theme.iconAbout)), "The Glorious About Node")
        act_warm  = menu.addAction(QIcon(Theme.icon(Theme.iconWarm)),  "The Comfortable Warm Node")
        act_text  = menu.addAction(QIcon(Theme.icon(Theme.iconText)),  "The Simple Text Node")
        act_read  = menu.addAction(QIcon(Theme.icon(Theme.iconTree)),  "The Read Me")
        act_about.triggered.connect(self._spawn_about_node)
        act_warm.triggered.connect(self._spawn_warm_node)
        act_text.triggered.connect(self._spawn_text_node)
        act_read.triggered.connect(self._spawn_readme_node)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_visual_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the visual group button."""
        menu = self._styled_menu()
        act_bezier  = menu.addAction(QIcon(Theme.icon(Theme.iconBezier)),  "The Prestigious Bezier Node")
        act_palette = menu.addAction(QIcon(Theme.icon(Theme.iconPalette)), "Palette")
        act_bezier.triggered.connect(self._spawn_bezier_node)
        act_palette.triggered.connect(self._spawn_palette_node)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_health_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the health group button."""
        menu = self._styled_menu()
        act_health = menu.addAction(QIcon(Theme.icon(Theme.iconHealth)), "Health Node")
        act_perf   = menu.addAction(QIcon(Theme.icon(Theme.iconPerf)), "Paint Performance Monitor")
        act_log    = menu.addAction(QIcon(Theme.icon(Theme.iconLog, fallback_color="#8aaa88")), "Tinkerbells Tail")
        act_health.triggered.connect(self._spawn_health_node)
        act_perf.triggered.connect(self._spawn_perf_node)
        act_log.triggered.connect(self._spawn_log_node)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_tools_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the tools group button."""
        menu = self._styled_menu()
        act_snip    = menu.addAction(QIcon(Theme.icon(Theme.iconSnip,    fallback_color="#c0a888")), "Snip a Wire")
        act_restore = menu.addAction(QIcon(Theme.icon(Theme.iconRestore, fallback_color="#8aaa88")), "Restore Last Deleted")
        act_tree    = menu.addAction(QIcon(Theme.icon(Theme.iconTree,    fallback_color="#8888aa")), "Folder Structure")
        act_info    = menu.addAction(QIcon(Theme.icon(Theme.iconInfo,    fallback_color="#9a9aaa")), "Info Node")
        act_snip.triggered.connect(self._start_wire_snip)
        act_restore.triggered.connect(self._restore_deleted)
        act_tree.triggered.connect(self._spawn_tree_node)
        act_info.triggered.connect(self._spawn_info_node)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_claude_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the Claude group button."""
        menu = self._styled_menu()
        act_claude   = menu.addAction(QIcon(Theme.icon(Theme.iconClaudeNode,     fallback_color="#7a9a7a")), "Claude Node")
        act_census   = menu.addAction(QIcon(Theme.icon(Theme.iconClaudeCensus,   fallback_color="#7a9a7a")), "Claude Token Census")
        act_response = menu.addAction(QIcon(Theme.icon(Theme.iconClaudeResponse, fallback_color="#555566")), "Claude Response Node")
        act_response.setEnabled(False)
        act_response.setToolTip("This node is invoked from inside the Claude Node")
        act_claude.triggered.connect(self._spawn_claude_node)
        act_census.triggered.connect(self._spawn_claude_info_node)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_images_menu(self, btn: QPushButton) -> None:
        """Pop a styled context menu under the images group button."""
        menu = self._styled_menu()

        img_action = menu.addAction(
            QIcon(Theme.icon(Theme.iconImage)), "Image Node"
        )
        vid_action = menu.addAction(
            QIcon(Theme.icon(Theme.iconVideo)), "Video Node"
        )
        seq_action = menu.addAction(
            QIcon(Theme.icon(Theme.iconSequence)), "Image Sequence Scrubber"
        )
        val_action = menu.addAction(
            QIcon(Theme.icon(Theme.iconValue)), "Value Node"
        )

        img_action.triggered.connect(self._spawn_image_node)
        vid_action.triggered.connect(self._spawn_video_node)
        seq_action.triggered.connect(self._spawn_sequence_node)
        val_action.triggered.connect(self._spawn_value_node)

        # Show below the button, left-aligned
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
    def _spawn_perf_node(self):        self._spawn(self.scene.add_perf_node,         "watching the paint loop")
    def _spawn_claude_info_node(self): self._spawn(self.scene.add_claude_info_node,  "counting every token with pride")

    def _spawn_tree_node(self):
        path = self._session_path()
        # session lives in {project}/Documents/data/ — project root is three levels up
        project_root = path.parent.parent.parent if path else None
        self._spawn(self.scene.add_tree_node, "mapping the territory",
                    project_path=str(project_root) if project_root else "")

    def _spawn_info_node(self):
        self._spawn(self.scene.add_info_node, "version 0.0.5")

    # =========================================================================
    # The buttons and stuff at the bottom of the Ui
    # =========================================================================

    def _setupBottomToolbar(self):
        self.bottomToolbar = QWidget()
        self.bottomToolbar.setFixedHeight(Theme.handleHeightBottom)

        outer = QVBoxLayout(self.bottomToolbar)
        outer.setContentsMargins(*Theme.layoutMargins)
        outer.setSpacing(2)

        # ── Info bar row ──────────────────────────────────────────────────────
        _info_bar_row = QWidget()
        _info_bar_row.setFixedHeight(26)
        _info_bar_row.setStyleSheet("background: transparent;")
        _info_bar_layout = QHBoxLayout(_info_bar_row)
        _info_bar_layout.setContentsMargins(0, 0, 0, 0)
        _info_bar_layout.setSpacing(0)

        self.info_label = pretty_label("", alignment=Qt.AlignCenter)
        self.info_label.setStyleSheet(
            f"background: transparent; border: none; padding: 0px 4px;"
            f" color: {Theme.textPrimary}; font-family: Chandler42; font-size: 16px;"
        )
        self.info_label.setFixedHeight(26)

        self._info_opacity = QGraphicsOpacityEffect()
        self._info_opacity.setOpacity(0.0)
        self.info_label.setGraphicsEffect(self._info_opacity)
        self._info_anim         = None
        self._info_click_action = None
        self._info_timer = QTimer(self)
        self._info_timer.setSingleShot(True)
        self._info_timer.timeout.connect(self._fade_info_out)
        self.info_label.mousePressEvent = (
            lambda e: self._info_click_action() if self._info_click_action else None
        )

        _info_bar_layout.addWidget(self.info_label, stretch=1)
        outer.addWidget(_info_bar_row)

        # ── Buttons row ───────────────────────────────────────────────────────
        buttons_row = QWidget()
        buttons_row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(buttons_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)

        layout.addStretch()

        # ── Zoom slider — horizontal, maps 0.1–5.0 to integer range ──────
        self._zoom_slider = pretty_slider(
            Qt.Horizontal,
            range=(10, 500),
            value=100,
            fixedWidth=250,
            singleStep=5,
            pageStep=25,
            valueChanged=self._on_zoom_slider,
        )
        layout.addWidget(self._zoom_slider, alignment=Qt.AlignVCenter)

        # Exid button — lower-right anchor, styled via PrettyButton
        self._exid_btn = button("Exid", clicked=self.close)
        layout.addWidget(self._exid_btn, alignment=Qt.AlignVCenter)

        outer.addWidget(buttons_row, stretch=1)

        self.grid.addWidget(self.bottomToolbar, 2, 0)

    def _on_zoom_slider(self, value: int) -> None:
        """Slider dragged — set the view zoom to the slider's value."""
        target = value / 100.0
        current = self.view.current_zoom
        if abs(target - current) < 0.001:
            return
        factor = target / current
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        self.view._apply_zoom(factor, anchor=centre)

    def show_info(self, message: str, on_click=None) -> None:
        """Typewriter reveal with simultaneous fade-in, hold 3 s, then fade out."""
        self._info_timer.stop()
        if hasattr(self, '_tw_timer') and self._tw_timer is not None:
            self._tw_timer.stop()

        self._tw_full    = message
        self._tw_index   = 0
        self._info_click_action = on_click
        self.info_label.setText("")
        self.info_label.setCursor(
            Qt.PointingHandCursor if on_click else Qt.ArrowCursor
        )

        # Fade in over the expected typing duration so opacity climbs with the text
        fade_ms = max(400, len(message) * 55)
        self._animate_info_opacity(0.0, 1.0, fade_ms)

        self._tw_timer = QTimer(self)
        self._tw_timer.setSingleShot(True)
        self._tw_timer.timeout.connect(self._typewriter_tick)
        self._tw_timer.start(random.randint(20, 60))

    def _typewriter_tick(self) -> None:
        self._tw_index += 1
        self.info_label.setText(self._tw_full[:self._tw_index])
        if self._tw_index < len(self._tw_full):
            # Irregular delay: short for most chars, occasional longer pause
            delay = random.choices(
                [random.randint(25, 65), random.randint(80, 160)],
                weights=[85, 15]
            )[0]
            self._tw_timer.start(delay)
        else:
            self._tw_timer = None
            self._info_timer.start(3000)

    def _fade_info_out(self) -> None:
        self._info_click_action = None
        self.info_label.setCursor(Qt.ArrowCursor)
        self._animate_info_opacity(1.0, 0.0, 600)

    def _animate_info_opacity(self, start: float, end: float, duration: int) -> None:
        if self._info_anim:
            self._info_anim.stop()
        self._info_anim = QPropertyAnimation(self._info_opacity, b"opacity")
        self._info_anim.setDuration(duration)
        self._info_anim.setStartValue(start)
        self._info_anim.setEndValue(end)
        self._info_anim.start()

    def _sync_zoom_slider(self) -> None:
        """Called after wheel-zoom to keep the slider in sync with the view."""
        value = int(round(self.view.current_zoom * 100))
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(max(10, min(500, value)))
        self._zoom_slider.blockSignals(False)

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
        """Show a warm status message in the bottom info bar."""
        self.show_info(text.capitalize())

    # =========================================================================
    # Sessions
    # =========================================================================

    def _session_path(self, project: str | None = None) -> Path | None:
        """Return the session.json path for a project folder name."""
        name = project if project is not None else self.project_selector.currentText()
        return session_path(name) if name else None

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

    def _get_viewport(self) -> dict:
        """Capture current camera position and zoom for session persistence."""
        try:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            return {
                "camera_x": center.x(),
                "camera_y": center.y(),
                "camera_zoom": self.view.current_zoom,
            }
        except (RuntimeError, AttributeError):
            return {}

    def _apply_viewport(self, vp: dict) -> None:
        """Restore camera position and zoom from a session viewport dict."""
        cx   = vp.get("camera_x")
        cy   = vp.get("camera_y")
        zoom = vp.get("camera_zoom")
        if cx is None or cy is None:
            return
        self.view._expand_scene_rect()
        if zoom is not None and zoom > 0:
            self.view.resetTransform()
            self.view.scale(zoom, zoom)
            self.view.current_zoom = zoom
        self.view.centerOn(QPointF(cx, cy))
        self._sync_zoom_slider()

    def _load_session_into_scene(self, path: Path | None) -> None:
        """Change cwd to the project folder and load its session."""
        if not path:
            return
        enter_project(path)
        if path.exists():
            vp = self.scene.load_session(path)
            if vp:
                QTimer.singleShot(0, lambda: self._apply_viewport(vp))

    def _autosave(self) -> None:
        """Save the current canvas to the active project's session.json."""
        path = self._session_path()
        if path:
            ensure_dir(path.parent)
            self.scene.save_session(path, self._get_viewport())

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
        self._init_autosave()
        self._load_session_into_scene(self._session_path())
        QTimer.singleShot(0, self._restore_camera)
        QTimer.singleShot(0, self._restore_pinned_preview)

    def on_session_changed(self) -> None:
        """Save the outgoing session, swap to a fresh scene, load incoming."""
        new_project = self.project_selector.currentText()

        # Save whatever was on canvas for the previous project
        if hasattr(self, '_active_project'):
            prev_path = self._session_path(self._active_project)
            if prev_path:
                ensure_dir(prev_path.parent)
                self.scene.save_session(prev_path, self._get_viewport())

        self._active_project = new_project
        set_value("ui", "selected_project", new_project)

        # Fresh scene — avoids re-entrant Qt teardown on live nodes
        self._swap_scene()
        self._load_session_into_scene(self._session_path(new_project))
        self._status(f"welcome back to {new_project}")

    def populate_sessions(self) -> None:
        desktop = Path.home() / "Desktop"
        desktop_folders = sorted(
            p.name for p in desktop.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ) if desktop.exists() else []
        self.project_selector.addItems(desktop_folders)
        saved = get("ui", "selected_project", "")
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
        """Move window gently when dragging the top bar.

        When curtains are rolled up the strip acts as a vertical slider —
        horizontal position is locked so it only glides up and down.
        """
        if self._dragging_window:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos
            if self.is_collapsed:
                delta.setX(0)
                # Clamp so the strip never leaves the visible desktop.
                # Reserve space at the bottom for an auto-hide taskbar —
                # the difference between full screen and available geometry
                # tells us the taskbar height; fall back to 48px if it's hidden.
                full   = self.screen().geometry()
                avail  = self.screen().availableGeometry()
                taskbar_h = max(full.height() - avail.height(), 48)
                new_y = max(avail.top(), self.pos().y() + delta.y())
                new_y = min(new_y, full.bottom() - self.height() - taskbar_h + 5)
                self.move(self.pos().x(), new_y)
            else:
                self.move(self.pos() + delta)
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
        if not self._shown_once:
            self._shown_once = True
            self._animate_fade_in()
            QTimer.singleShot(250, lambda: self.show_info(
                f"{appName} is generally so happy that you are here. ✨"
            ))
            QTimer.singleShot(600, self._check_vaporize_restart)
            if getattr(self, '_pending_fullscreen', False):
                self._pending_fullscreen = False
                QTimer.singleShot(0, self.showFullScreen)
        else:
            self.setWindowOpacity(1.0)

    def _animate_opacity(self, start: float, end: float, duration: int,
                          easing, on_finish=None) -> QPropertyAnimation:
        """Create, start, and return a windowOpacity animation."""
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        if on_finish is not None:
            anim.finished.connect(on_finish)
        anim.start()
        return anim

    def _animate_fade_in(self) -> None:
        """Fade the window opacity from 0 → 1 on show."""
        self.fadeIn = self._animate_opacity(0.0, 1.0, 200, QEasingCurve.OutCubic)

    def _check_vaporize_restart(self):
        """Spawn a response node if the previous session ended via 'then vaporize'."""
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
            self._pending_fullscreen = True  # applied in showEvent after first show

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
        """Remove all __pycache__ folders and .pyc files under the project root."""
        clean_pycache()

    def _persist_claude_node_size(self) -> None:
        nodes = [n for n in self.scene.items() if isinstance(n, ClaudeNode)]
        if nodes:
            node = nodes[-1]
            w = max(200.0, min(800.0, node.rect().width()))
            h = max(250.0, min(700.0, node.rect().height()))
            set_nested("node", "claude", "default_width",  w)
            set_nested("node", "claude", "default_height", h)

    def _run_exit_script(self) -> None:
        logger.info(random.choice(motivationalMessages))
        _main_module = sys.modules.get('__main__')
        if _main_module is not None and getattr(_main_module, '_instance_lock', None) is not None:
            try:
                _main_module._instance_lock.close()
            except OSError:
                pass
            _main_module._instance_lock = None

    def _spawn_restart(self) -> None:
        """Launch the next session. Called after the fade-out completes."""
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
                import threading
                threading.Thread(target=self._cleanup_pycache, daemon=True).start()
                self._persist_claude_node_size()
            except (RuntimeError, Exception):
                pass
            event.accept()
            return

        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
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
        """Fade the window opacity from current → 0, spawn the next session, then close."""
        def _on_faded():
            self._spawn_restart()
            self.close()
        self.fadeOut = self._animate_opacity(
            self.windowOpacity(), 0.0, 120, QEasingCurve.InCubic, on_finish=_on_faded
        )
