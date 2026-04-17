#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main_window.py main application window
-One day it woke up and dreamt of becoming a frameless window with draggable toolbars and a node graphics view for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import random
import time

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QGraphicsScene, QGraphicsView, QSplitter, QSizePolicy, QProgressBar, QLabel, QFrame, QScrollArea, QGraphicsOpacityEffect, QSystemTrayIcon, QMenu, QDialog
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QPointF, QSize, QRect, QEvent, QTimer
from graphics.Scene import IntricateScene
from graphics.View import IntricateView
from pretty_widgets.graphics.Theme import Theme
from nodes.ClaudeNode import ClaudeNode
from nodes.ImageNode import ImageNode
from pretty_widgets.PrettyButton import button
from pretty_widgets.PrettyMenu import menu as pretty_menu
from pretty_widgets.utils.logger import setup_logger
from utils.PhrasePicker import motivationalMessages
from pretty_widgets.utils.settings import appName, set_nested, get_nested, set_value, get
from utils.helpers import ensure_dir, clean_pycache
from utils.session import session_path, enter_project
from pretty_widgets.PrettyCombo import combo as pretty_combo
from pretty_widgets.PrettyLabel import label as pretty_label
from pretty_widgets.PrettySlider import slider as pretty_slider

logger = setup_logger()


class _ButtonBar(QWidget):
    """
    Pins a left group of widgets to the left edge and a right group to the right
    edge using resizeEvent geometry calls — bypasses all layout-manager expansion
    completely. A progress bar floats in the gap between them.
    """
    def __init__(self, left: QWidget, right: QWidget, progress: QWidget, parent=None):
        super().__init__(parent)
        self._left     = left
        self._right    = right
        self._progress = progress
        left.setParent(self)
        right.setParent(self)
        progress.setParent(self)
        self.setFixedHeight(max(left.minimumSizeHint().height(),
                                right.minimumSizeHint().height()))

    def _reposition(self):
        w  = self.width()
        h  = self.height()
        lw = self._left.minimumSizeHint().width()
        rw = self._right.minimumSizeHint().width()
        lh = self._left.minimumSizeHint().height()
        rh = self._right.minimumSizeHint().height()
        self._left.setGeometry(0,       (h - lh) // 2, lw, lh)
        self._right.setGeometry(w - rw, (h - rh) // 2, rw, rh)
        gap = 10
        px  = lw + gap
        pw  = max(0, w - lw - rw - gap * 2)
        self._progress.setGeometry(px, (h - 8) // 2, pw, 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def event(self, e):
        if e.type() == e.Type.LayoutRequest:
            self._reposition()
        return super().event(e)


class _NewSessionDialog(QDialog):
    """Frameless new-session dialog matching the app's visual language."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)

        # ── Outer container with background + border ─────────────────────
        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget#newSessionContainer {{
                background: {Theme.windowBg};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 9px;
            }}
        """)
        container.setObjectName("newSessionContainer")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Label ────────────────────────────────────────────────────────
        lbl = QLabel("Name your next masterpiece:")
        lbl.setStyleSheet(f"""
            color: {Theme.textPrimary};
            font-family: '{Theme.healthFontFamily}';
            font-size: {Theme.healthFontSizeLabel}pt;
        """)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # ── Text input ───────────────────────────────────────────────────
        from pretty_widgets.PrettyMenu import StyledLineEdit
        self._input = StyledLineEdit()
        self._input.setPlaceholderText("Urzula\u2026")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 5px;
                padding: 6px 10px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
        """)
        self._input.returnPressed.connect(self.accept)
        layout.addWidget(self._input)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = button("Create")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

        self._input.setFocus()

    def name(self) -> str:
        return self._input.text()


class IntricateApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 1. The civil pleasantries
        self.setWindowTitle("Our Love As Intricate As The Patterns We Impose")
        self.setStyleSheet(f"QMainWindow {{ background-color: {Theme.windowBg}; }}")
        self.setWindowOpacity(0.0)

        # 2. The Beautiful and Prestigious Top Toolbar things with all it's specifics
        self._dragging_window = False
        self._resizing_window = False
        self._drag_pos = None
        self.is_collapsed = False
        self._is_fullscreen = False
        self._shown_once = False

        # 3.  Window OS Defaults
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(500, 500)
        
        # 4. Grid and widget setup
        self._setup_grid()
        self._build_top_toolbar()
        self.sidebar = self._build_sidebar()
        self._setupCentralArea()
        self._setupBottomToolbar()

        # 5. Repaint non-canvas widgets solid so WA_TranslucentBackground
        #    only punches through the canvas, not the toolbars/sidebar.
        self._make_opaque(self.top_toolbar)
        self._make_opaque(self.bottomToolbar)
        if hasattr(self, 'sidebar'):
            self._make_opaque(self.sidebar)
        if hasattr(self, 'rightPanel'):
            self._make_opaque(self.rightPanel)

        # 6. Restore persisted geometry
        self._restore_geometry()

        # 7. Keyboard shortcuts
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+A"), self, self._select_chain)

        # 8. Load session for the initially selected project, then start autosave
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

    @staticmethod
    def _make_opaque(widget):
        """Force a widget to paint its background solid, defeating WA_TranslucentBackground."""
        from PySide6.QtGui import QPalette
        widget.setAutoFillBackground(True)
        pal = widget.palette()
        pal.setColor(QPalette.Window, QColor(Theme.windowBg))
        widget.setPalette(pal)

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
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Project selector: absolute child at fixed x=550 ─────────────────
        combo = self.setup_project_selector()
        combo.setParent(self.top_toolbar)

        # All toolbar buttons share the same size from Theme
        _btn = Theme.toolbarBtnSize
        _ico = QSize(Theme.toolbarBtnIconSize, Theme.toolbarBtnIconSize)

        self._curtains_btn = self.setup_iconic_button(
            clicked=self.toggle_curtains,
        )
        self._curtains_btn.setFixedSize(_btn, _btn)
        self._curtains_btn.setIconSize(_ico)
        self._curtains_btn.setParent(self.top_toolbar)

        # Dock watcher — polls the window behind while curtains are rolled up
        self._dock_watcher = QTimer(self)
        self._dock_watcher.setInterval(500)
        self._dock_watcher.timeout.connect(self._check_window_behind)
        self._last_docked_exe = ""

        # ── Tray / Maximize / Exit buttons: absolute children, pinned right ──
        self._tray_btn = self.setup_iconic_button(
            clicked=self._minimize_to_tray, icon=Theme.iconTray
        )
        self._tray_btn.setFixedSize(_btn, _btn)
        self._tray_btn.setIconSize(_ico)
        self._tray_btn.setParent(self.top_toolbar)
        self._tray_btn.setToolTip("Minimize to tray")
        from pretty_widgets.PrettyTooltip import install_tooltip
        install_tooltip(self._tray_btn)

        self._max_btn = self.setup_iconic_button(
            clicked=self.toggle_fullscreen, icon=Theme.iconMaximize
        )
        self._max_btn.setFixedSize(_btn, _btn)
        self._max_btn.setIconSize(_ico)
        self._max_btn.setParent(self.top_toolbar)
        self._max_btn.setToolTip("Maximize")
        install_tooltip(self._max_btn)

        self._exit_btn = self.setup_iconic_button(
            clicked=self.close, icon=Theme.iconClose
        )
        self._exit_btn.setFixedSize(_btn, _btn)
        self._exit_btn.setIconSize(_ico)
        self._exit_btn.setParent(self.top_toolbar)
        self._exit_btn.setToolTip("Exid, not a typo.  It's an exit button named exid")
        install_tooltip(self._exit_btn)
        # Deferred first position — toolbar width isn't known at construction time
        QTimer.singleShot(0, self._reposition_exit_btn)

        self._setup_system_tray()

        self.grid.addWidget(self.top_toolbar, 0, 0, 1, 2)  # span both columns
        self.top_toolbar.installEventFilter(self)
        self.top_toolbar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.top_toolbar.customContextMenuRequested.connect(
            lambda pos: self._show_toolbar_context_menu(self.top_toolbar.mapToGlobal(pos))
        )

    def _reposition_exit_btn(self) -> None:
        """Keep the tray / maximize / exit buttons pinned to the top-right corner."""
        if not hasattr(self, '_exit_btn') or not hasattr(self, 'top_toolbar'):
            return
        tb  = self.top_toolbar
        gap = Theme.toolbarBtnGap
        y   = (tb.height() - self._exit_btn.height()) // 2

        # Project selector — fixed at Theme.toolbarTitleX
        if hasattr(self, 'project_selector'):
            cy = (tb.height() - self.project_selector.height()) // 2
            self.project_selector.move(Theme.toolbarTitleX, cy)
            self.project_selector.raise_()

        # Curtains button — fixed at Theme.toolbarCurtainsX
        if hasattr(self, '_curtains_btn'):
            cy = (tb.height() - self._curtains_btn.height()) // 2
            self._curtains_btn.move(Theme.toolbarCurtainsX, cy)
            self._curtains_btn.raise_()

        # Exit button flush right
        ex = tb.width() - self._exit_btn.width() - Theme.toolbarRightMargin
        self._exit_btn.move(ex, y)
        self._exit_btn.raise_()

        # Maximize button left of exit
        if hasattr(self, '_max_btn'):
            mx = ex - self._max_btn.width() - gap
            self._max_btn.move(mx, y)
            self._max_btn.raise_()
        else:
            mx = ex

        # Tray button left of maximize
        if hasattr(self, '_tray_btn'):
            tx = mx - self._tray_btn.width() - gap
            self._tray_btn.move(tx, y)
            self._tray_btn.raise_()

    def _setup_system_tray(self) -> None:
        """Create the system tray icon with a restore / exit context menu."""
        self._tray_icon = QSystemTrayIcon(self)
        from pathlib import Path as _Path
        _sticker = _Path(__file__).resolve().parent / "Images" / "Stickers" / "Intricate Official Iconic Icon.png"
        if _sticker.exists():
            self._tray_icon.setIcon(QIcon(QPixmap(str(_sticker))))
        else:
            icon = Theme.icon(Theme.iconCurtains)
            self._tray_icon.setIcon(QIcon(icon) if icon and not icon.isNull() else self.windowIcon())

        from pretty_widgets.PrettyMenu import PrettyMenu
        tray_menu = PrettyMenu(self)
        tray_menu.addAction("Show", self._restore_from_tray)
        tray_menu.addSeparator()
        tray_menu.addAction("Exit", self.close)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _minimize_to_tray(self) -> None:
        """Hide the window and show the system tray icon."""
        self._tray_icon.show()
        self.hide()

    def _restore_from_tray(self) -> None:
        """Bring the window back from the system tray."""
        self.show()
        self.raise_()
        self.activateWindow()
        self._tray_icon.hide()

    def _on_tray_activated(self, reason) -> None:
        """Double-click or trigger on the tray icon restores the window."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_from_tray()

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
        # Joy wake — deliberate button press only. No passive interaction wake.
        # The sleep/wake button is the sole controller of the sleep state.
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        screen = self.screen().geometry()
        if self.geometry() == screen:
            # Already filling the screen — restore
            if hasattr(self, '_pre_fullscreen_geometry'):
                self.setGeometry(self._pre_fullscreen_geometry)
            self._is_fullscreen = False
        else:
            # Not filling the screen — maximize regardless of flag state
            self._pre_fullscreen_geometry = self.geometry()
            self.setGeometry(screen)
            self._is_fullscreen = True

    # =========================================================================
    # Toolbar context menu — hidden unlock/lock for folder management
    # =========================================================================

    _folders_unlocked = False

    def _show_toolbar_context_menu(self, global_pos) -> None:
        """Right-click the top toolbar to unlock/lock project folders."""
        menu = self._styled_menu()
        if self._folders_unlocked:
            act = menu.addAction("Lock Folders")
            act.setToolTip("Re-acquire working directory lock on the active project")
            act.triggered.connect(self._lock_folders)
        else:
            act = menu.addAction("Unlock Folders")
            act.setToolTip("Release directory locks so folders can be deleted in Explorer")
            act.triggered.connect(self._unlock_folders)
        menu.exec(global_pos)

    def _unlock_folders(self) -> None:
        """Release all directory locks so folders can be deleted in Explorer.

        Releases:
        1. Process CWD — Windows holds a directory handle on it
        2. Python's import machinery caches — gc.collect() clears stale refs
        3. Any cached Path objects or open scandir iterators
        """
        import gc

        safe_dir = Path(__file__).resolve().parent
        try:
            os.chdir(str(safe_dir))
            logger.info("[unlock] CWD moved to %s", safe_dir)
        except OSError:
            pass

        # Force garbage collection to release any stale Path iterators,
        # open scandir handles, or cached directory references
        gc.collect()

        # Nudge Windows into releasing cached directory notifications
        # by touching the CWD — some directory handles linger until the
        # OS processes a new directory operation on the same thread
        try:
            os.listdir(str(safe_dir))
        except OSError:
            pass

        logger.info("[unlock] folders released — safe to delete in Explorer")
        self._folders_unlocked = True

    def _lock_folders(self) -> None:
        """Re-acquire the CWD lock by chdir-ing back to the active project."""
        path = self._session_path()
        if path:
            from utils.session import project_root_from_session
            project_root = project_root_from_session(path)
            if project_root.exists():
                try:
                    os.chdir(str(project_root))
                    logger.info("[lock] CWD restored to %s", project_root)
                except OSError:
                    pass
        self._folders_unlocked = False

    # =========================================================================
    # Curtains, The Window Rollup Thing
    # =========================================================================

    def toggle_curtains(self):
        """Animate the window into a sleek HUD strip.

        Ordering is critical — the animation object must be created and
        configured BEFORE the hide/show calls, which must happen BEFORE
        start().  This is the sequence that makes Qt yield the layout
        row to the geometry animation for a graceful roll in both
        directions.  Do not reorder.
        """
        fw = self.focusWidget()
        if fw:
            fw.clearFocus()

        # ① Unlock the window to shrink past its natural minimum
        self.setMinimumHeight(0)

        # ② Create and configure the animation BEFORE hiding/showing
        self.view.setTransformationAnchor(QGraphicsView.NoAnchor)
        collapsing = not self.is_collapsed
        start_rect = self.geometry()
        self.curtain_anim = QPropertyAnimation(self, b"geometry")
        self.curtain_anim.setDuration(
            Theme.windowRollTimingUp if collapsing else Theme.windowRollTimingDown
        )
        self.curtain_anim.setEasingCurve(
            getattr(QEasingCurve, Theme.windowRollEasing, QEasingCurve.OutExpo)
        )

        if collapsing:
            self.original_height = self.height()
            end_rect = QRect(start_rect.x(), start_rect.y(),
                             start_rect.width(), Theme.handleHeightTop)
            # ③ Delay-hide so the bottom toolbar is visible during the roll start
            QTimer.singleShot(200, self._sidebar_splitter.hide)
            if self.scene:
                self.scene.pause_all_videos()
            self._last_docked_exe = ""
            self._dock_watcher.start()
        else:
            self._dock_watcher.stop()
            self._stop_hunger_glow()
            # Clamp so the bottom edge never drops below the screen
            avail = self.screen().availableGeometry()
            y = min(start_rect.y(), avail.bottom() - self.original_height + 1)
            y = max(avail.top(), y)
            end_rect = QRect(start_rect.x(), y,
                             start_rect.width(), self.original_height)
            # ③ Show content AFTER animation exists but BEFORE start()
            self._sidebar_splitter.show()

        # ④ Arm and fire
        self.curtain_anim.setStartValue(start_rect)
        self.curtain_anim.setEndValue(end_rect)
        self.curtain_anim.finished.connect(self._on_curtains_settled)
        self.curtain_anim.start()

        self.is_collapsed = not self.is_collapsed

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

        if not self.is_collapsed:
            self.view._notify_viewport_changed()


    def _get_dock_offsets(self) -> dict:
        """Read app-specific dock offsets from settings.toml [intricate.dock_offsets].

        Each key is a lowercase exe name, value is the Y offset in px from screen top.
        Only apps listed here are eligible for dock snapping — unlisted apps are ignored.

        Example settings.toml entry:
            [intricate.dock_offsets]
            "claude.exe" = 0
            "chrome.exe" = 50
        """
        import pretty_widgets.utils.settings as _s
        return _s.get("intricate", "dock_offsets", default={})

    def _toggle_dock_position(self) -> None:
        """Glide the rolled-up strip to a Y position based on the app behind it."""
        if not self.is_collapsed:
            return
        from utils.window_behind import get_window_behind
        info = get_window_behind(int(self.winId()))
        exe_raw = (info.get("exe", "") if info else "").lower()
        exe = exe_raw.removesuffix(".exe")
        offsets = self._get_dock_offsets()

        if exe not in offsets:
            # App not in the privileged list — just show what's behind, don't move
            if info:
                self.show_info(f"{info['exe']} (not docked)")
            return

        offset = offsets[exe]
        target_y = self.screen().availableGeometry().top() + offset

        start_rect = self.geometry()
        end_rect = QRect(start_rect.x(), target_y, start_rect.width(), start_rect.height())
        self._dock_anim = QPropertyAnimation(self, b"geometry")
        self._dock_anim.setDuration(250)
        self._dock_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._dock_anim.setStartValue(start_rect)
        self._dock_anim.setEndValue(end_rect)
        self._dock_anim.start()

        if info:
            self.show_info(f"{info['exe']} — {info['title']}")

    def _check_window_behind(self) -> None:
        """Periodic check — auto-dock when the app behind changes."""
        if not self.is_collapsed:
            return
        from utils.window_behind import get_window_behind
        info = get_window_behind(int(self.winId()))
        exe_raw = (info.get("exe", "") if info else "").lower()
        exe = exe_raw.removesuffix(".exe")
        if exe == self._last_docked_exe:
            return  # same app, nothing to do
        self._last_docked_exe = exe
        offsets = self._get_dock_offsets()
        # Desktop / no window behind → park at top edge; known app → use its offset
        offset = offsets.get(exe, 0)
        target_y = self.screen().availableGeometry().top() + offset
        if self.pos().y() == target_y:
            return  # already in position
        start_rect = self.geometry()
        end_rect = QRect(start_rect.x(), target_y, start_rect.width(), start_rect.height())
        self._dock_anim = QPropertyAnimation(self, b"geometry")
        self._dock_anim.setDuration(250)
        self._dock_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._dock_anim.setStartValue(start_rect)
        self._dock_anim.setEndValue(end_rect)
        self._dock_anim.start()

    # =================================================================================
    # The central area — sidebar | canvas | reserved for a special vip arriving later
    # =================================================================================

    def _setupCentralArea(self):
        """
        The central shelf — three zones in a horizontal QSplitter:

            Left  — NodeSidebar: icon buttons for node creation
            Center — IntricateView: the infinite canvas
            Right  — Reserved: the VIP arrives later (page renderer)

        QSplitter gives us the harmonica — drag the divider to collapse
        or expand any zone. The right zone starts at zero width until needed.
        """
        self.scene = IntricateScene()
        self.view  = IntricateView(self.scene)
        self.view._on_zoom_changed = lambda: self._sync_zoom_slider()

        # ── Right panel — image preview zone ──────────────────────────────────
        self.rightPanel = self._build_preview_panel()

        # ── Inner horizontal splitter — canvas + preview ─────────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Theme.windowBg};
            }}
        """)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.rightPanel)
        for i in range(1, self.splitter.count()):
            handle = self.splitter.handle(i)
            if handle:
                handle.setCursor(Qt.ArrowCursor)

        # Canvas takes all slack; preview zone follows its own minimum
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(1, True)

        QTimer.singleShot(0, self._restore_preview_width)

        # ── Vertical splitter — canvas above, bottom toolbar below ────────────
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(4)
        self._v_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Theme.windowBg};
            }}
        """)
        self._v_splitter.addWidget(self.splitter)
        # bottomToolbar is added later by _setupBottomToolbar

        # ── Outer horizontal splitter — sidebar | canvas area ─────────────────
        # Draggable divider lets the user collapse/expand the sidebar.
        self._sidebar_splitter = QSplitter(Qt.Horizontal)
        self._sidebar_splitter.setHandleWidth(4)
        self._sidebar_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Theme.windowBg};
            }}
        """)
        self._sidebar_splitter.addWidget(self.sidebar)
        self._sidebar_splitter.addWidget(self._v_splitter)
        self._sidebar_splitter.setStretchFactor(0, 0)
        self._sidebar_splitter.setStretchFactor(1, 1)
        self._sidebar_splitter.setCollapsible(0, True)
        self._sidebar_splitter.setCollapsible(1, False)

        self.grid.addWidget(self._sidebar_splitter, 1, 0, 1, 2)

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
        from pretty_widgets.PrettyTooltip import install_tooltip
        install_tooltip(self._pin_btn)
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
        """Restore saved preview panel width from settings."""
        saved_preview = get("ui", "preview_width", None)
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and saved_preview is not None:
            total = sizes[0] + sizes[1]
            self.splitter.setSizes([max(0, total - saved_preview), saved_preview])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """Persist preview panel width whenever the splitter moves."""
        sizes = self.splitter.sizes()
        if len(sizes) == 2:
            set_value("ui", "preview_width", sizes[1])

    def _restore_bottom_height(self) -> None:
        """Restore saved bottom toolbar height from settings."""
        saved = get("ui", "bottom_height", None)
        if saved is not None:
            sizes = self._v_splitter.sizes()
            if len(sizes) == 2:
                total = sizes[0] + sizes[1]
                self._v_splitter.setSizes([total - saved, saved])
        self._v_splitter.splitterMoved.connect(self._on_v_splitter_moved)

    def _on_v_splitter_moved(self, _pos: int, _index: int) -> None:
        """Persist bottom toolbar height whenever the vertical splitter moves."""
        sizes = self._v_splitter.sizes()
        if len(sizes) == 2:
            set_value("ui", "bottom_height", sizes[1])

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

    def _select_chain(self) -> None:
        """Select all nodes connected to the current selection via wires."""
        from nodes.BaseNode import BaseNode
        seeds = [item for item in self.scene.selectedItems()
                 if isinstance(item, BaseNode)]
        if not seeds:
            return
        visited = set()
        queue = list(seeds)
        while queue:
            node = queue.pop(0)
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            for conn in node.connections:
                for neighbor in (conn.start_node, conn.end_node):
                    if neighbor and neighbor is not node and id(neighbor) not in visited:
                        queue.append(neighbor)
        for node in self.scene.items():
            if isinstance(node, BaseNode) and id(node) in visited:
                node.setSelected(True)

    def _on_selection_changed(self) -> None:
        """Update the preview panel when selection changes — skipped while pinned."""
        if self._preview_pinned:
            return
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return  # scene's C++ side torn down during mass-delete
        for item in items:
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

        from pretty_widgets.PrettyTooltip import install_tooltip

        sidebar = QWidget()
        sidebar.setFixedWidth(Theme.sidebarWidth())
        sidebar.setStyleSheet(f"background-color: {Theme.windowBg};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(
            Theme.sidebarPadding, 0,
            Theme.sidebarPadding, Theme.sidebarPadding
        )
        layout.setSpacing(Theme.sidebarButtonGap)

        def _cat_btn(icon_name, tooltip, menu_fn):
            """Category button — icon fills the entire button, no Qt frame overhead."""
            sz = Theme.iconButtonSize
            b = button(icon_name=icon_name, tooltip=tooltip)
            b.setFixedSize(sz, sz)
            b.setIconSize(QSize(sz, sz))
            b.setFlat(True)
            b.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")
            b.clicked.connect(lambda _=None, btn=b: menu_fn(btn))
            install_tooltip(b)
            layout.addWidget(b, alignment=Qt.AlignHCenter)

        _cat_btn(Theme.iconText,        "Text",   self._show_text_menu)
        _cat_btn(Theme.iconImagesGroup,  "Images", self._show_images_menu)
        _cat_btn(Theme.iconAudioGroup,   "Audio",  self._show_audio_menu)
        _cat_btn(Theme.iconVisualGroup,  "Visual", self._show_visual_menu)
        _cat_btn(Theme.iconHealthGroup,  "Health", self._show_health_menu)
        _cat_btn(Theme.iconToolsGroup,   "Tools",  self._show_tools_menu)
        _cat_btn(Theme.iconInfoGroup,    "Info",   self._show_info_menu)
        _cat_btn(Theme.iconClaude,       "Claude", self._show_claude_menu)

        # ── Stretch pushes slider/bar to the bottom ───────────────────────────
        layout.addStretch()

        # ── Fog slider ────────────────────────────────────────────────────────
        # Vertical, top = opaque (255), bottom = transparent (0).
        # Placeholder — will drive fog layer alpha when that arrives.
        import pretty_widgets.utils.settings as _s
        _fog_init = int(_s.get_nested("intricate", "canvas", "fog_alpha", 180))
        self.fog_slider = pretty_slider(
            Qt.Vertical,
            handle_icon="slider_handle_vertical.png",
            handle_size=28,
            range=(0, 255),
            value=_fog_init,
            invertedAppearance=False,
            fixedWidth=Theme.sidebarWidth() - Theme.sidebarPadding * 2,
            minimumHeight=80,
            valueChanged=self._on_fog_slider_changed,
        )
        layout.addWidget(self.fog_slider, alignment=Qt.AlignHCenter)

        layout.addSpacing(4)

        # ── Joy bucket — own bottom-anchored container ────────────────────────
        # Separated from the top category buttons so stretch works between them.
        sz = Theme.iconButtonSize

        joy_container = QWidget()
        joy_container.setStyleSheet("background-color: transparent;")
        joy_layout = QVBoxLayout(joy_container)
        joy_layout.setContentsMargins(0, 0, 0, 0)
        joy_layout.setSpacing(0)
        joy_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

        self.joy_bar = QProgressBar()
        self.joy_bar.setOrientation(Qt.Vertical)
        self.joy_bar.setRange(0, 100)
        self.joy_bar.setValue(int(_s.get_nested("intricate", "joy", "bar_value", 100)))
        self.joy_bar.setTextVisible(False)
        self.joy_bar.setFixedWidth(sz // 3)
        self.joy_bar.setMinimumHeight(sz * 2)
        self.joy_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {Theme.backDrop};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                    stop:0 #1e1e1e, stop:0.4 #5c3e4f,
                    stop:0.7 #a56a85, stop:1 #d87a9e);
                border-radius: 2px;
            }}
        """)
        joy_layout.addWidget(self.joy_bar, alignment=Qt.AlignHCenter)
        joy_layout.addStretch()

        # Feed button — dynamic radial shadow, physical press depth
        from widgets.StickerButton import StickerButton
        clean_pix = Theme.icon(Theme.iconCatnipFeedClean, fallback_color="#d87a9e")
        self._feed_btn = StickerButton(clean_pix, sz, parent=joy_container)
        self._feed_btn.setToolTip("Feed me")
        install_tooltip(self._feed_btn)
        self._feed_btn.pressed.connect(self._on_feed_pressed)
        self._feed_btn.released.connect(self._on_feed_released)
        joy_layout.addWidget(self._feed_btn, alignment=Qt.AlignHCenter)

        # Sleep toggle — small and gentle
        self._sleep_btn = button("", clicked=self._toggle_joy_sleep)
        self._sleep_btn.setMinimumSize(0, 0)
        self._sleep_btn.setFixedSize(QSize(24, 24))
        self._sleep_btn.setFlat(True)
        self._sleep_btn.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")
        self._sleep_btn.setText("\U0001f319")  # 🌙
        self._sleep_btn.setToolTip("Tuck me in")
        install_tooltip(self._sleep_btn)
        joy_layout.addWidget(self._sleep_btn, alignment=Qt.AlignHCenter)

        layout.addWidget(joy_container)

        # ── Joy bucket counter ─────────────────────────────────────────────
        import pretty_widgets.utils.settings as _s
        self._joy_bucket_count = int(_s.get_nested("intricate", "joy", "buckets", 0))
        self._joy_happy_secs   = float(_s.get_nested("intricate", "joy", "happy_secs", 0.0))
        self._joy_bucket_label = pretty_label(
            str(self._joy_bucket_count),
            alignment=Qt.AlignCenter,
        )
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())
        install_tooltip(self._joy_bucket_label)
        self._joy_bucket_label.setStyleSheet(f"color: {Theme.textPrimary}; font-size: 10pt;")
        layout.addWidget(self._joy_bucket_label, alignment=Qt.AlignHCenter)

        layout.addSpacing(Theme.sidebarPadding)

        # Feed rate limit — 3 meals per rolling 10-minute window
        self._feed_timestamps: list[float] = []
        self._FEED_WINDOW   = 600.0       # 10 minutes in seconds
        self._FEED_MAX      = 3           # meals allowed per window

        # Depletion timer — drains 1% every 36 seconds (100% over 1 hour)
        # Sleep mode slows to 360 seconds per tick (10 hours full drain)
        self._joy_hungry = False          # dirty flag — cleared by any feed click
        self._joy_sleeping = False        # sleep mode — slower depletion
        self._JOY_AWAKE_INTERVAL  = 36000   # 36s per tick  → 1 hour
        self._JOY_SLEEP_INTERVAL  = 360000  # 360s per tick → 10 hours
        self._joy_timer = QTimer(self)
        self._joy_timer.setInterval(self._JOY_AWAKE_INTERVAL)
        self._joy_timer.timeout.connect(self._deplete_joy)
        self._joy_timer.start()

        # Grace + happy accumulator — ticks every second while at 100%
        self._JOY_GRACE_SECS      = 600     # 10 minutes of grace before depletion
        self._JOY_BUCKET_SECS     = 3600    # 1 hour of total happy time = +1 bucket
        self._joy_grace_remaining = 0.0     # seconds left in current grace window
        self._joy_in_grace        = False   # True while bar is 100% and grace active
        self._happy_timer = QTimer(self)
        self._happy_timer.setInterval(1000)  # 1-second resolution
        self._happy_timer.timeout.connect(self._tick_happy)

        # If we launch at 100%, start the grace immediately
        if self.joy_bar.value() == 100:
            self._begin_grace()

        # App-wide event filter — any mouse/key interaction wakes from sleep
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

        # Install PrettyTooltip on all sidebar children that have a tooltip set
        from pretty_widgets.PrettyTooltip import install_tooltips
        install_tooltips(sidebar)

        return sidebar

    def _on_fog_slider_changed(self, value: int) -> None:
        """Drive canvas fog transparency and persist to settings."""
        self.view._fog_alpha = value
        self.view.viewport().update()
        import pretty_widgets.utils.settings as _s
        _s.set_nested("intricate", "canvas", "fog_alpha", value)

    def _on_feed_pressed(self) -> None:
        """Mouse down — StickerButton handles the depth shift visually."""
        pass

    def _on_feed_released(self) -> None:
        """Mouse up — trigger the feed action."""
        self._feed_joy()

    def _feed_joy(self) -> None:
        """Feed the joy bucket — any click resets the timer and clears hunger.

        Rate-limited to 3 feeds per rolling 10-minute window.
        It's stuffed beyond that — can only eat so much at a time.
        """
        # Already full — didn't eat anything, don't count it
        if self.joy_bar.value() >= 100:
            return

        now = time.monotonic()
        # Prune timestamps outside the window
        self._feed_timestamps = [
            t for t in self._feed_timestamps
            if now - t < self._FEED_WINDOW
        ]
        if len(self._feed_timestamps) >= self._FEED_MAX:
            return                        # stuffed — can't eat any more right now

        self._feed_timestamps.append(now)
        v = min(100, self.joy_bar.value() + 10)
        self.joy_bar.setValue(v)
        self._joy_hungry = False
        self._stop_hunger_glow()
        # Reset the depletion timer so feeding buys a full cycle of peace
        if hasattr(self, '_joy_timer') and self._joy_timer.isActive():
            self._joy_timer.start()
        # If we just hit 100%, start the grace period (happy time begins)
        if v == 100 and not self._joy_in_grace:
            self._begin_grace()

    def _toggle_joy_sleep(self) -> None:
        """Put the joy system to sleep or wake it up."""
        if self._joy_sleeping:
            self._wake_joy()
        else:
            self._sleep_joy()

    def _sleep_joy(self) -> None:
        """Enter sleep mode — slow depletion, muted meows."""
        self._joy_sleeping = True
        self._joy_timer.setInterval(self._JOY_SLEEP_INTERVAL)
        self._joy_timer.start()          # restart with new interval
        self._sleep_btn.setText("\u2600\ufe0f")  # ☀️ — press to wake
        self._sleep_btn.setToolTip("Wake me up")

    def _wake_joy(self) -> None:
        """Exit sleep mode — normal depletion resumes."""
        if not self._joy_sleeping:
            return
        self._joy_sleeping = False
        self._joy_timer.setInterval(self._JOY_AWAKE_INTERVAL)
        self._joy_timer.start()          # restart with new interval
        self._sleep_btn.setText("\U0001f319")  # 🌙 — press to sleep
        self._sleep_btn.setToolTip("Tuck me in")

    # ─────────────────────────────────────────────────────────────────────────
    # HAPPY ACCUMULATOR — time spent at 100% earns joy buckets
    # ─────────────────────────────────────────────────────────────────────────

    def _joy_bucket_tooltip(self) -> str:
        """Build a tooltip showing bucket count and progress to next."""
        mins = int(self._joy_happy_secs) // 60
        secs = int(self._joy_happy_secs) % 60
        return f"{self._joy_bucket_count} joy buckets  —  {mins}m {secs}s happy toward next"

    def _begin_grace(self) -> None:
        """Start the grace period — bar is at 100%, happy time begins."""
        self._joy_in_grace = True
        self._joy_grace_remaining = self._JOY_GRACE_SECS
        self._happy_timer.start()

    def _end_grace(self) -> None:
        """Grace expired — bar will start depleting on next timer tick."""
        self._joy_in_grace = False
        self._happy_timer.stop()

    def _tick_happy(self) -> None:
        """Called every second while at 100%. Accumulates happy time."""
        if self.joy_bar.value() < 100:
            # Shouldn't happen, but guard against it
            self._end_grace()
            return

        # Count this second as happy time
        self._joy_happy_secs += 1.0

        # Update tooltip with live progress
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())

        # Check if we earned a bucket
        if self._joy_happy_secs >= self._JOY_BUCKET_SECS:
            self._joy_happy_secs -= self._JOY_BUCKET_SECS
            self._joy_bucket_count += 1
            self._joy_bucket_label.setText(str(self._joy_bucket_count))
            self._persist_happy()

        # Burn down the grace window
        self._joy_grace_remaining -= 1.0
        if self._joy_grace_remaining <= 0:
            self._end_grace()

        # Persist happy progress periodically (every 30 seconds)
        if int(self._joy_happy_secs) % 30 == 0:
            self._persist_happy()

    def _persist_happy(self) -> None:
        """Save happy accumulator and bucket count to settings."""
        import pretty_widgets.utils.settings as _s
        _s.set_nested("intricate", "joy", "happy_secs", round(self._joy_happy_secs, 1))
        _s.set_nested("intricate", "joy", "buckets", self._joy_bucket_count)
        _s.set_nested("intricate", "joy", "bar_value", self.joy_bar.value())

    def _deplete_joy(self) -> None:
        """Drain 1% from the joy bucket. Meow with escalating urgency.

        While in grace (bar at 100%), depletion is suppressed — the happy
        accumulator handles the countdown instead.
        """
        if self._joy_in_grace:
            return                        # grace period absorbs this tick
        v = max(0, self.joy_bar.value() - 1)
        self.joy_bar.setValue(v)
        if not self._joy_sleeping:
            self._maybe_meow(v)
        # Flip dirty once below threshold; feeding is the only way back
        if v < 15 and not self._joy_hungry:
            self._joy_hungry = True
        if self._joy_hungry and self.is_collapsed:
            self._start_hunger_glow()
        elif not self._joy_hungry:
            self._stop_hunger_glow()

    def _maybe_meow(self, hunger_pct: int) -> None:
        """Play a meow from audio/meows/ based on hunger level.

        Files are sorted alphabetically — early files are gentle, later
        files are demanding.  As the bar drops, meows get more frequent
        and pick from further down the escalation ladder.

        Frequency:  >70% silent, 50-70% rare, 30-50% occasional, <30% frequent.
        """
        import random
        from utils.audio import audio
        if audio.is_muted() or hunger_pct > 70:
            return

        # Frequency gates — higher hunger = more likely to meow per tick
        if hunger_pct > 50 and random.random() > 0.15:
            return
        if hunger_pct > 30 and random.random() > 0.30:
            return
        if hunger_pct > 10 and random.random() > 0.50:
            return

        self._play_meow(hunger_pct)

    def _play_meow(self, hunger_pct: int) -> None:
        """Pick and play a meow WAV matching the current hunger tier."""
        from pathlib import Path
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect
        import random

        meow_dir = Path(__file__).resolve().parent / "audio" / "meows"
        if not meow_dir.exists():
            return
        wavs = sorted(meow_dir.glob("*.wav"))
        if not wavs:
            return

        # Map hunger to escalation tier — lower hunger picks later (angrier) files
        n = len(wavs)
        if hunger_pct > 50:
            pool = wavs[:max(1, n // 3)]           # gentle third
        elif hunger_pct > 25:
            pool = wavs[n // 3:max(n // 3 + 1, 2 * n // 3)]  # middle third
        else:
            pool = wavs[2 * n // 3:]                # demanding third
        if not pool:
            pool = wavs

        chosen = random.choice(pool)

        if not hasattr(self, '_meow_sfx'):
            self._meow_sfx = QSoundEffect(self)
        self._meow_sfx.setSource(QUrl.fromLocalFile(str(chosen)))
        self._meow_sfx.setVolume(0.5)
        self._meow_sfx.play()

    # ─────────────────────────────────────────────────────────────────────────
    # HUNGER GLOW — gentle toolbar pulse when the joy bucket is starving
    # ─────────────────────────────────────────────────────────────────────────

    def _start_hunger_glow(self) -> None:
        """Begin a gentle looping glow on the toolbar to ask for attention."""
        if hasattr(self, '_glow_timer') and self._glow_timer.isActive():
            return  # already glowing

        self._glow_phase = 0.0
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(50)  # 20fps
        self._glow_timer.timeout.connect(self._tick_hunger_glow)
        self._glow_timer.start()

    def _tick_hunger_glow(self) -> None:
        """Animate a soft breathing glow on the toolbar background."""
        import math
        self._glow_phase += 0.04  # slow breath
        # Sine wave 0→1→0 for a gentle pulse
        t = (math.sin(self._glow_phase) + 1.0) / 2.0
        # Blend from windowBg toward a warm accent
        bg = QColor(Theme.windowBg)
        accent = QColor("#5c3e4f")  # muted rose from the progress bar gradient
        r = int(bg.red()   + (accent.red()   - bg.red())   * t * 0.4)
        g = int(bg.green() + (accent.green() - bg.green()) * t * 0.4)
        b = int(bg.blue()  + (accent.blue()  - bg.blue())  * t * 0.4)
        self.top_toolbar.setStyleSheet(f"background-color: rgb({r},{g},{b});")

    def _stop_hunger_glow(self) -> None:
        """Stop the hunger glow and restore the toolbar to its natural color."""
        if hasattr(self, '_glow_timer') and self._glow_timer.isActive():
            self._glow_timer.stop()
        self.top_toolbar.setStyleSheet(f"background-color: {Theme.windowBg};")

    # ─────────────────────────────────────────────────────────────────────────
    # NODE SPAWN ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _viewport_center(self):
        """Current viewport center in scene coordinates."""
        vp = self.view.viewport()
        return self.view.mapToScene(vp.width() // 2, vp.height() // 2)

    def _spawn(self, add_fn, status_msg: str, **kwargs):
        """Place a node at the viewport centre and update the status bar."""
        try:
            node = add_fn(pos=self._viewport_center(), **kwargs)
        except Exception:
            logger.exception("Failed to spawn node via %s", add_fn.__name__)
            return None
        from utils.audio import audio
        audio.play_chime()
        self._status(status_msg)
        return node

    def _spawn_warm_node(self):        self._spawn(self.scene.add_warm_node,         "a warm thought arrives")
    def _spawn_about_node(self):       self._spawn(self.scene.add_about_node,        "a little note for later")
    def _spawn_bezier_node(self):      self._spawn(self.scene.add_bezier_node,       "curves ahead")
    def _spawn_health_node(self):      self._spawn(self.scene.add_health_node,       "checking in on things")
    def _spawn_claude_node(self):      self._spawn(self.scene.add_claude_node,       "claude has entered the chat")
    def _spawn_image_node(self):       self._spawn(self.scene.add_image_node,        "a picture is worth everything")
    def _spawn_video_node(self):       self._spawn(self.scene.add_video_node,        "lights, camera, action")
    def _spawn_text_node(self):        self._spawn(self.scene.add_text_node,         "words, words, words")
    def _spawn_cushions_node(self):    self._spawn(self.scene.add_cushions_node,     "fluffing the cushions")
    def _spawn_code_node(self):        self._spawn(self.scene.add_code_node,         "compiling the vibes")
    def _spawn_bloom_node(self):       self._spawn(self.scene.add_bloom_node,        "particles are blooming")
    def _spawn_null_node(self):        self._spawn(self.scene.add_null_node,         "a point in space")
    def _spawn_log_node(self):         self._spawn(self.scene.add_log_node,          "tailing the log")

    def _spawn_readme_node(self) -> None:
        """Spawn a text node pre-filled with README.md from the session project root."""
        path = self._session_path()
        if not path:
            return
        readme = path.parent.parent.parent / "README.md"
        if not readme.exists():
            self._status("no README.md found in project root")
            return
        try:
            text = readme.read_text(encoding="utf-8")
        except Exception:
            self._status("could not read README.md")
            return
        self._spawn(self.scene.add_readme_node, "the README has arrived",
                    label=text)
    def _spawn_architecture_node(self): self._spawn(self.scene.add_architecture_node, "the blueprint unfolds")
    def _spawn_node_schema_node(self): self._spawn(self.scene.add_node_schema_node,  "the schema reveals itself")
    def _spawn_registry_node(self):    self._spawn(self.scene.add_registry_node,     "the vocabulary opens")
    def _spawn_sequence_node(self):    self._spawn(self.scene.add_sequence_node,     "ready to scrub")
    def _spawn_value_node(self):       self._spawn(self.scene.add_value_node,        "dialing in the value")
    def _spawn_sticker_node(self):     self._spawn(self.scene.add_sticker_node,      "sticker time")
    def _spawn_fbx_node(self):         self._spawn(self.scene.add_fbx_node,          "vertices from thin air")
    def _spawn_palette_node(self):     self._spawn(self.scene.add_palette_node,      "mixing colors")
    def _spawn_wormhole_node(self):   self._spawn(self.scene.add_wormhole_node,     "ready to open the portal")

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
        menu = pretty_menu(self)
        menu.setToolTipsVisible(False)
        menu.hovered.connect(self._menu_tooltip_delay)
        menu.aboutToHide.connect(self._cancel_menu_tooltip)
        return menu

    def _menu_tooltip_delay(self, action):
        """Show action tooltip after a 2-second delay."""
        from functools import partial
        # Cancel any pending tooltip
        self._cancel_menu_tooltip()
        tip = action.toolTip()
        if not tip or tip == action.text():
            return
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(1000)
        self._tooltip_timer.timeout.connect(partial(self._show_menu_tooltip, tip))
        self._tooltip_timer.start()

    def _show_menu_tooltip(self, text):
        from PySide6.QtGui import QCursor
        from pretty_widgets.PrettyTooltip import PrettyTooltip
        PrettyTooltip.instance().show_tip(text, QCursor.pos())

    def _cancel_menu_tooltip(self):
        if hasattr(self, '_tooltip_timer'):
            self._tooltip_timer.stop()
            try:
                self._tooltip_timer.timeout.disconnect()
            except RuntimeError:
                pass
        from pretty_widgets.PrettyTooltip import PrettyTooltip
        t = PrettyTooltip.instance()
        if t.isVisible():
            t.hide()

    # ─────────────────────────────────────────────────────────────────────────
    # REGISTRY-DRIVEN MENUS
    # ─────────────────────────────────────────────────────────────────────────

    # Dispatch map: node type_key → spawn callable.
    # Built lazily on first menu open so all spawn methods are defined.
    _spawn_dispatch: dict | None = None

    # Action dispatch: action_key → callable
    _action_dispatch: dict | None = None

    def _ensure_dispatch(self) -> None:
        if self._spawn_dispatch is not None:
            return
        self._spawn_dispatch = {
            "about":         self._spawn_about_node,
            "warm":          self._spawn_warm_node,
            "text":          self._spawn_text_node,
            "cushions":      self._spawn_cushions_node,
            "code":          self._spawn_code_node,
            "bloom":         self._spawn_bloom_node,
            "null":          self._spawn_null_node,
            "image":         self._spawn_image_node,
            "video":         self._spawn_video_node,
            "sequence":      self._spawn_sequence_node,
            "fbx":           self._spawn_fbx_node,
            "audio":         self._spawn_audio_node,
            "merge":         self._spawn_merge_node,
            "audio_hold":    self._spawn_audio_hold_node,
            "bezier":        self._spawn_bezier_node,
            "palette":       self._spawn_palette_node,
            "value":         self._spawn_value_node,
            "sticker":       self._spawn_sticker_node,
            "health":        self._spawn_health_node,
            "perf":          self._spawn_perf_node,
            "log":           self._spawn_log_node,
            "joy_stats":     self._spawn_joy_stats_node,
            "git":           self._spawn_git_node,
            "tree":          self._spawn_tree_node,
            "session":       self._spawn_session_node,
            "info":          self._spawn_info_node,
            "readme":        self._spawn_readme_node,
            "architecture":  self._spawn_architecture_node,
            "node_schema":   self._spawn_node_schema_node,
            "registry":      self._spawn_registry_node,
            "claude":        self._spawn_claude_node,
            "claude_info":   self._spawn_claude_info_node,
            "wormhole":      self._spawn_wormhole_node,
        }
        self._action_dispatch = {
            "restore":           self._restore_deleted,
            "snip":              self._start_wire_snip,
            "launch_claude":     self._launch_claude_app,
            "launch_claude_code": self._launch_claude_code,
        }

    def _show_category_menu(self, category: str, btn: QPushButton) -> None:
        """Build a category menu from node_registry.toml entries."""
        from utils import registry

        self._ensure_dispatch()
        menu = self._styled_menu()

        # Non-node actions first (e.g. Restore, Snip in tools)
        for key, entry in registry.get_actions_by_category(category):
            icon_attr = entry.get("icon", "")
            fallback = entry.get("icon_fallback", "#6b5a47")
            icon_val = getattr(Theme, icon_attr, None)
            pix = Theme.icon(icon_val, fallback_color=fallback) if icon_val else Theme.icon(None)
            act = menu.addAction(QIcon(pix), entry.get("name", key))
            tip = entry.get("tooltip", "")
            if tip:
                act.setToolTip(tip)
            handler = self._action_dispatch.get(key)
            if handler:
                act.triggered.connect(handler)

        # Node entries
        for key, entry in registry.get_nodes_by_category(category):
            icon_attr = entry.get("icon", "")
            fallback = entry.get("icon_fallback", "#6b5a47")
            icon_val = getattr(Theme, icon_attr, None)
            pix = Theme.icon(icon_val, fallback_color=fallback) if icon_val else Theme.icon(None)
            act = menu.addAction(QIcon(pix), entry.get("name", key))
            tip = entry.get("tooltip", "")
            if tip:
                act.setToolTip(tip)
            spawnable = entry.get("spawnable", True)
            if not spawnable:
                act.setEnabled(False)
            handler = self._spawn_dispatch.get(key)
            if handler and spawnable:
                act.triggered.connect(handler)

        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_text_menu(self, btn):    self._show_category_menu("text", btn)
    def _show_images_menu(self, btn):  self._show_category_menu("images", btn)
    def _show_audio_menu(self, btn):   self._show_category_menu("audio", btn)
    def _show_visual_menu(self, btn):  self._show_category_menu("visual", btn)
    def _show_health_menu(self, btn):  self._show_category_menu("health", btn)
    def _show_tools_menu(self, btn):   self._show_category_menu("tools", btn)
    def _show_info_menu(self, btn):
        """Info menu: registry entries + dynamic Documents/*.md files."""
        from pathlib import Path
        from utils import registry

        self._ensure_dispatch()
        menu = self._styled_menu()

        # Registry-driven entries (same as _show_category_menu)
        for key, entry in registry.get_nodes_by_category("info"):
            icon_attr = entry.get("icon", "")
            fallback = entry.get("icon_fallback", "#6b5a47")
            icon_val = getattr(Theme, icon_attr, None)
            pix = Theme.icon(icon_val, fallback_color=fallback) if icon_val else Theme.icon(None)
            act = menu.addAction(QIcon(pix), entry.get("name", key))
            tip = entry.get("tooltip", "")
            if tip:
                act.setToolTip(tip)
            spawnable = entry.get("spawnable", True)
            if not spawnable:
                act.setEnabled(False)
            handler = self._spawn_dispatch.get(key)
            if handler and spawnable:
                act.triggered.connect(handler)

        # Dynamic Documents/ entries — top-level .md files + nested subfolders
        docs_dir = Path(__file__).resolve().parent / "Documents"
        _DEDICATED = {"Architecture.md", "Node Type Schema.md"}
        _SKIP_DIRS = {"data"}
        if docs_dir.is_dir():
            fallback_pix = Theme.icon(Theme.iconSession, fallback_color="#8a9aaa")

            def _make_doc_action(target_menu, md_path):
                act = target_menu.addAction(QIcon(fallback_pix), md_path.stem)
                def _spawn_doc(_, p=md_path):
                    try:
                        text = p.read_text(encoding="utf-8")
                    except Exception:
                        self._status(f"could not read {p.name}")
                        return
                    # Scatter the doc directly — the MarkdownNode is the
                    # parsing engine, self-destructs after splitting.
                    from nodes.MarkdownNode import MarkdownNode
                    from data.MarkdownNodeData import MarkdownNodeData
                    from PySide6.QtCore import QPointF, QTimer
                    from PySide6.QtWidgets import QGraphicsRectItem
                    data = MarkdownNodeData(label=text)
                    node = MarkdownNode(data)
                    node.setPos(QPointF(-999_999, -999_999))
                    node.setVisible(False)
                    self.scene.addItem(node)
                    node._split_into_nodes()
                    # Self-destruct — sever interaction flags, then remove
                    # on the next event loop tick (TreeNode zombie pattern).
                    node.setSelected(False)
                    node.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
                    scene = self.scene
                    QTimer.singleShot(0, lambda: scene.removeItem(node))
                    from utils.audio import audio
                    audio.play_chime()
                    self._status(f"{p.stem} unfolds")
                act.triggered.connect(_spawn_doc)

            # Top-level .md files (excluding dedicated nodes)
            top_mds = sorted(
                p for p in docs_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".md" and p.name not in _DEDICATED
            )
            if top_mds:
                menu.addSeparator()
                for md_path in top_mds:
                    _make_doc_action(menu, md_path)

            # Subdirectory submenus
            subdirs = sorted(
                d for d in docs_dir.iterdir()
                if d.is_dir() and d.name not in _SKIP_DIRS
            )
            if subdirs:
                if not top_mds:
                    menu.addSeparator()
                for subdir in subdirs:
                    sub_mds = sorted(
                        p for p in subdir.iterdir()
                        if p.is_file() and p.suffix.lower() == ".md"
                    )
                    if sub_mds:
                        submenu = self._styled_menu()
                        for md_path in sub_mds:
                            _make_doc_action(submenu, md_path)
                        menu.addMenu(submenu).setText(subdir.name)

        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
    def _show_claude_menu(self, btn):  self._show_category_menu("claude", btn)

    def _launch_claude_app(self) -> None:
        """Launch or focus+maximize the Claude desktop app."""
        import ctypes
        user32 = ctypes.windll.user32

        # Look for an existing Claude window
        hwnd = user32.FindWindowW(None, None)
        found = 0
        while hwnd:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if "Claude" in buf.value and "Intricate" not in buf.value:
                        found = hwnd
                        break
            hwnd = user32.GetWindow(hwnd, 2)

        if found:
            user32.ShowWindow(found, 3)  # SW_MAXIMIZE
            user32.SetForegroundWindow(found)
        else:
            # Claude ships as an MSIX package on Windows — versioned install path
            # under Program Files\WindowsApps is unreadable and changes on every
            # update.  Launch by AppUserModelID instead; this is the stable handle.
            import subprocess, os
            AUMID = r"Claude_pzs8sxrjxfjjc!Claude"
            try:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{AUMID}"])
            except Exception:
                try:
                    os.startfile("claude://")          # last-resort URL protocol
                except Exception:
                    return
            self._poll_maximize_window("Claude", user32)

    def _launch_claude_code(self) -> None:
        """Resume the Intricate Claude Code session in the MSIX desktop app.

        Uses the `claude://` URL protocol directly — specifically the
        Resume deep-link, which was reverse-engineered from the MSIX
        app's bundled URL router:

            case Iu.Resume:
              const s = searchParams.get("session");
              ra.importCliSession(s).then(o =>
                  dispatcher.dispatchNavigate(ra.getSessionRoute(o)));

        Handing a Claude Code session UUID to that handler makes the
        app import the CLI session and navigate to its session route,
        which for a Code session is the Code tab.  Net effect:

          - No subprocess, no PowerShell, no stdin hijack
          - No stale AnthropicClaude path (MSIX-style versioned install)
          - No visible terminal, no manual /desktop typing
          - Handoff is a single OS-level URL dispatch

        Pairs symmetrically with _launch_claude_app: both resolve to
        the same single-instance MSIX window, in different tab modes.
        Clicking either while the other is active swaps the mode in
        place — a free Chat/Code toggle between the two sidebar entries.
        """
        import os, ctypes
        CONV_UUID = "365b40dd-0a0a-422a-9550-a7867716dc81"
        try:
            os.startfile(f"claude://resume/?session={CONV_UUID}")
        except OSError:
            return  # claude:// protocol handler not registered

        # MSIX app typically focuses itself on deep-link receipt, but belt
        # and braces: poll+maximize the window like Launch Claude does.
        user32 = ctypes.windll.user32
        self._poll_maximize_window("Claude", user32)

    def _poll_maximize_window(self, title_substring: str, user32) -> None:
        """Poll for a window matching *title_substring* to appear, then maximize it."""
        attempts = [0]
        timer = QTimer()
        timer.setInterval(500)

        def _check():
            import ctypes
            attempts[0] += 1
            hwnd = user32.FindWindowW(None, None)
            while hwnd:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if title_substring in buf.value and "Intricate" not in buf.value:
                            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                            user32.SetForegroundWindow(hwnd)
                            timer.stop()
                            return
                hwnd = user32.GetWindow(hwnd, 2)
            if attempts[0] >= 20:
                timer.stop()

        timer.timeout.connect(_check)
        timer.start()
    def _spawn_perf_node(self):        self._spawn(self.scene.add_perf_node,         "watching the paint loop")
    def _spawn_joy_stats_node(self):   self._spawn(self.scene.add_joy_stats_node,    "inspecting the joy bucket")
    def _spawn_claude_info_node(self): self._spawn(self.scene.add_claude_info_node,  "counting every token with pride")

    def _spawn_tree_node(self):
        path = self._session_path()
        # session lives in {project}/Documents/data/ — project root is three levels up
        project_root = path.parent.parent.parent if path else None
        self._spawn(self.scene.add_tree_node, "mapping the territory",
                    project_path=str(project_root) if project_root else "")

    def _spawn_info_node(self):
        self._spawn(self.scene.add_info_node, "version 0.3.0")

    def _spawn_git_node(self):
        self._spawn(self.scene.add_git_node, "Remember to say the product name!")

    def _spawn_session_node(self):
        self._spawn(self.scene.add_session_node, "ready for a session file")

    def _spawn_audio_node(self):
        self._spawn(self.scene.add_audio_node, "Yummi >> Tummy >> voila!")

    def _spawn_merge_node(self):
        self._spawn(self.scene.add_merge_node, "converging streams")

    def _spawn_audio_hold_node(self):
        self._spawn(self.scene.add_audio_hold_node, "silence is golden")

    # =========================================================================
    # The buttons and stuff at the bottom of the Ui
    # =========================================================================

    def _setupBottomToolbar(self):
        self.bottomToolbar = QWidget()
        self.bottomToolbar.setStyleSheet(f"background: {Theme.windowBg};")

        outer = QVBoxLayout(self.bottomToolbar)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(4)

        # ── Info bar row ──────────────────────────────────────────────────────
        _info_bar_row = QWidget()
        _info_bar_row.setFixedHeight(28)
        _info_bar_row.setStyleSheet("background: transparent;")
        _info_bar_layout = QHBoxLayout(_info_bar_row)
        _info_bar_layout.setContentsMargins(0, 0, 0, 0)
        _info_bar_layout.setSpacing(0)

        self.info_label = pretty_label("", alignment=Qt.AlignCenter)
        self.info_label.setStyleSheet(
            f"background: transparent; border: none; padding: 0px 4px 0px 4px;"
            f" color: {Theme.textPrimary}; font-family: Chandler42; font-weight: 500; font-style: italic; font-size: 16px;"
        )
        self.info_label.setFixedHeight(28)

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

        # ── Left group — (empty for now) ──────────────────────────────────────
        left_group = QWidget()
        left_group.setStyleSheet("background: transparent;")
        left_layout = QHBoxLayout(left_group)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # ── Right group — zoom / Sound / Polaroid / eXid ─────────────────────
        right_group = QWidget()
        right_group.setStyleSheet("background: transparent;")
        right_layout = QHBoxLayout(right_group)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._zoom_slider = pretty_slider(
            Qt.Horizontal,
            use_scroll_icon=True,
            handle_size=28,
            range=(10, 500),
            value=100,
            fixedWidth=250,
            fixedHeight=32,
            singleStep=5,
            pageStep=25,
            valueChanged=self._on_zoom_slider,
        )
        right_layout.addWidget(self._zoom_slider)

        from utils.audio import audio
        self._mute_btn = button("Quiet" if audio.is_muted() else "Sound", clicked=self._toggle_global_mute)
        self._mute_btn.setMinimumSize(0, 0)
        self._mute_btn.setToolTip("Unmute all" if audio.is_muted() else "Mute all")
        mute_font = self._mute_btn.font()
        mute_font.setPointSize(16)
        self._mute_btn.setFont(mute_font)
        # Fix width so toggling Sound/Quiet doesn't shift the slider.
        # Reey glyphs extend well beyond QFontMetrics advance, so add generous room.
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(mute_font)
        widest = max(fm.horizontalAdvance("Sound"), fm.horizontalAdvance("Quiet"))
        self._mute_btn.setFixedWidth(widest + 32)  # padding + Reey overshoot
        self._mute_btn.setMinimumHeight(fm.height() + 6 + 18)  # top + bottom padding
        from utils.hover_glow import HoverGlow

        _mute_base = (
            f"QPushButton {{ background-color: {Theme.buttonBg};"
            f" border: none; border-radius: 6px;"
            f" padding: 6px 2px 18px 14px; }}"
        )
        HoverGlow.install(self._mute_btn, _mute_base)
        right_layout.addWidget(self._mute_btn)

        self._snap_btn = button("Polaroid", clicked=self._snapshot_viewport)
        self._snap_btn.setMinimumSize(0, 0)
        self._snap_btn.setToolTip("Snapshot viewport (alpha)")
        snap_font = self._snap_btn.font()
        snap_font.setPointSize(16)
        self._snap_btn.setFont(snap_font)
        _snap_base = (
            f"QPushButton {{ background-color: {Theme.buttonBg};"
            f" border: none; border-radius: 6px;"
            f" padding: 6px 2px 18px 4px; }}"
        )
        HoverGlow.install(self._snap_btn, _snap_base)
        right_layout.addWidget(self._snap_btn)

        # ── Progress bar — hidden at rest, floats between the two groups ──────
        self._bottom_progress = QProgressBar()
        self._bottom_progress.setRange(0, 100)
        self._bottom_progress.setValue(0)
        self._bottom_progress.setFixedHeight(8)
        self._bottom_progress.setTextVisible(False)
        self._bottom_progress.hide()
        self._bottom_progress.setStyleSheet(
            f"QProgressBar {{ background: {Theme.nodeBg}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {Theme.primaryBorder}; border-radius: 4px; }}"
        )

        buttons_row = _ButtonBar(left_group, right_group, self._bottom_progress)
        outer.addWidget(buttons_row)

        # Add to vertical splitter — canvas stretches, toolbar stays compact
        self._v_splitter.addWidget(self.bottomToolbar)
        self._v_splitter.setStretchFactor(0, 1)   # canvas takes all slack
        self._v_splitter.setStretchFactor(1, 0)   # toolbar keeps its size
        self._v_splitter.setCollapsible(0, False)  # never collapse the canvas
        self._v_splitter.setCollapsible(1, True)   # toolbar can collapse fully
        # Vertical split cursor so the handle is discoverable
        for i in range(1, self._v_splitter.count()):
            handle = self._v_splitter.handle(i)
            if handle:
                handle.setCursor(Qt.SplitVCursor)

        # Restore saved bottom bar height
        QTimer.singleShot(0, self._restore_bottom_height)

    def _on_zoom_slider(self, value: int) -> None:
        """Slider dragged — set the view zoom to the slider's value."""
        target = value / 100.0
        current = self.view.current_zoom
        if abs(target - current) < 0.001:
            return
        factor = target / current
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        self.view._apply_zoom(factor, anchor=centre)

    def _toggle_global_mute(self) -> None:
        """Toggle master mute — silences chimes and all video audio.

        On unmute, each media node fades from silence to its target volume
        over 1 s so the listener isn't hit with a sudden wall of sound.
        """
        from utils.audio import audio
        muted = not audio.is_muted()
        audio.set_muted(muted)
        self._mute_btn.setText("Quiet" if muted else "Sound")
        self._mute_btn.setToolTip("Unmute all" if muted else "Mute all")
        from nodes.VideoNode import VideoNode
        from nodes.AudioNode import AudioNode
        for item in self.scene.items():
            if isinstance(item, (VideoNode, AudioNode)):
                if muted or item.data.muted:
                    item._audio.setMuted(True)
                else:
                    # Gentle fade-in: drop volume to 0, unmute, then
                    # animate back to the node's target level.
                    item._audio.setVolume(0.0)
                    item._audio.setMuted(False)
                    item._fade_volume(0.0, item._target_volume)

    def _snapshot_viewport(self) -> None:
        """Capture the current viewport with transparent background."""
        from utils.helpers import snapshot_viewport
        path = snapshot_viewport(self.view, session_name=self.project_selector.currentText())
        if path:
            import os
            self.show_info(f"Snap saved → {path.name}", on_click=lambda: subprocess.Popen(["explorer", "/select,", str(path)]))

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
        # Ensure git repo exists — session file may predate git init
        project_dir = path.parent.parent.parent  # Documents/data/session → project root
        if project_dir.exists() and not (project_dir / ".git").exists():
            self._git_init_project(project_dir, project_dir.name)
        try:
            from utils.image_cache import set_cache_root
            set_cache_root(path.parent)
        except Exception:
            pass  # Cache setup failure is non-fatal
        # Suspend autosave during load — a partial load must never overwrite the
        # full session on disk.  Re-arm after the scene is fully populated.
        self._autosave_blocked = True
        self._autosave_timer.stop()
        if path.exists():
            vp = self.scene.load_session(path)
            if vp:
                QTimer.singleShot(0, lambda: self._apply_viewport(vp))
        # Unblock autosave after the initial scene.changed burst settles
        def _unblock():
            self._autosave_blocked = False
        QTimer.singleShot(3000, _unblock)

    def _autosave(self) -> None:
        """Save the current canvas to the active project's session.json."""
        if getattr(self, '_autosave_blocked', False):
            return
        if self.project_selector.currentText() == self._NEW_SESSION_SENTINEL:
            return
        # Never overwrite a session with an empty scene — protects against
        # save-on-close after a failed load wiping valid session data.
        from nodes.BaseNode import BaseNode
        has_nodes = any(isinstance(i, BaseNode) for i in self.scene.items())
        if not has_nodes:
            return
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
        self._autosave_blocked = True
        self._init_autosave()
        self._load_session_into_scene(self._session_path())
        QTimer.singleShot(0, self._restore_camera)
        QTimer.singleShot(0, self._restore_pinned_preview)

    def on_session_changed(self) -> None:
        """Save the outgoing session, swap to a fresh scene, load incoming."""
        new_project = self.project_selector.currentText()

        # ── Create New Session ───────────────────────────────────────────
        if new_project == self._NEW_SESSION_SENTINEL:
            self._create_new_session()
            return

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

    def _create_new_session(self) -> None:
        """Prompt for a name, create the folder, and switch to the new session."""
        prev = getattr(self, '_active_project', '')

        # Lower the window so the dialog isn't hidden behind always-on-top
        saved_flags = self.windowFlags()
        self.setWindowFlags(saved_flags & ~Qt.WindowStaysOnTopHint)
        self.show()

        # Roll up curtains for the cinematic reveal
        was_collapsed = False
        try:
            if hasattr(self, 'is_collapsed') and not self.is_collapsed:
                self.toggle_curtains()
                was_collapsed = True
        except Exception:
            pass

        dlg = _NewSessionDialog(parent=None)
        result = dlg.exec()

        # Roll curtains back down and restore window flags
        if was_collapsed:
            try:
                self.toggle_curtains()
            except Exception:
                pass
        self.setWindowFlags(saved_flags)
        self.show()
        self.raise_()

        name = dlg.name().strip() if result == QDialog.DialogCode.Accepted else ""

        if not name:
            # Cancelled or empty — restore previous selection
            self.project_selector.blockSignals(True)
            self.project_selector.setCurrentText(prev)
            self.project_selector.blockSignals(False)
            return

        # Check if folder already exists
        project_dir = Path.home() / "Desktop" / name
        if project_dir.exists():
            self._status(f"{name} already exists — switching to it")
        else:
            ensure_dir(project_dir / "Documents" / "data")
            self._git_init_project(project_dir, name)

        # Save outgoing session before switching
        if prev:
            prev_path = self._session_path(prev)
            if prev_path:
                ensure_dir(prev_path.parent)
                self.scene.save_session(prev_path, self._get_viewport())

        # Repopulate combo with the new folder included
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        self.populate_sessions()
        self.project_selector.setCurrentText(name)
        self.project_selector.blockSignals(False)

        self._active_project = name
        set_value("ui", "selected_project", name)

        self._swap_scene()
        self._load_session_into_scene(self._session_path(name))
        self._status(f"welcome to {name}")

    def _git_init_project(self, project_dir: Path, name: str) -> None:
        """git init + .gitignore + README + initial commit for a new project folder."""
        import subprocess as _sp
        try:
            _run = lambda cmd: _sp.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True, timeout=15
            )
            _run(["git", "init"])
            gitignore = project_dir / ".gitignore"
            gitignore.write_text(
                "__pycache__/\n*.pyc\n.env\n*.log\nlogs/\n",
                encoding="utf-8",
            )
            readme = project_dir / "README.md"
            readme.write_text(
                f"# {name}\n\nIt is what it is\n",
                encoding="utf-8",
            )
            _run(["git", "add", "."])
            _run(["git", "commit", "-m", f"init {name}"])
            logger.info(f"[session] git init complete for {name}")
        except Exception:
            logger.warning(f"[session] git init failed for {name}", exc_info=True)

    _NEW_SESSION_SENTINEL = "+ New Session"

    def populate_sessions(self) -> None:
        desktop = Path.home() / "Desktop"
        desktop_folders = sorted(
            p.name for p in desktop.iterdir()
            if p.is_dir() and not p.name.startswith(".")
            and p.name != self._NEW_SESSION_SENTINEL
            and p.name != "_runtime"
        ) if desktop.exists() else []
        self.project_selector.addItems(desktop_folders)
        self.project_selector.addItem(self._NEW_SESSION_SENTINEL)
        saved = get("ui", "selected_project", "")
        if saved in desktop_folders:
            self.project_selector.setCurrentText(saved)
        self._active_project = self.project_selector.currentText()
        self._fit_project_selector()

    def _fit_project_selector(self) -> None:
        """Resize the project selector to fit the longest item name."""
        fm = self.project_selector.fontMetrics()
        longest = 0
        for i in range(self.project_selector.count()):
            w = fm.horizontalAdvance(self.project_selector.itemText(i))
            if w > longest:
                longest = w
        # Fixed width — fills the space between anchor and curtains button.
        # Short names sit trimmer inside; long names use the full width.
        fixed_w = Theme.toolbarCurtainsX - Theme.toolbarTitleX - 4
        self.project_selector.setFixedWidth(fixed_w)

    # =========================================================================
    # Mouse and Hover Events
    # =========================================================================

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_exit_btn()

    _RESIZE_GRIP = 16   # px from bottom-right corner

    def _in_resize_grip(self, pos) -> bool:
        """True if pos is inside the passive bottom-right resize zone."""
        return (pos.x() >= self.width() - self._RESIZE_GRIP
                and pos.y() >= self.height() - self._RESIZE_GRIP)

    def mousePressEvent(self, event):
        """The Curtains Sensor: Every single press counts. (coming soon!)"""
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            # Bottom-right corner resize grip
            if self._in_resize_grip(pos):
                self._resizing_window = True
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
            if pos.y() < Theme.handleHeightTop:
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
        if self._resizing_window:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos
            new_w = max(self.minimumWidth(),  self.width()  + delta.x())
            new_h = max(self.minimumHeight(), self.height() + delta.y())
            self.resize(new_w, new_h)
            self._drag_pos = new_pos
            event.accept()
            return
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
        self._resizing_window = False
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
            if getattr(self, '_pending_fullscreen', False):
                self._pending_fullscreen = False
                self.showFullScreen()
            # Enable DWM Mica blur behind the transparent canvas
            from graphics.Scene import enable_blur
            enable_blur(int(self.winId()), tint=QColor(Theme.backDrop))
            self._animate_fade_in()
            QTimer.singleShot(250, lambda: self.show_info(
                f"{appName} is generally so happy that you are here. ✨"
            ))
            QTimer.singleShot(600, self._check_vaporize_restart)

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
        self.fadeIn = self._animate_opacity(0.0, 1.0, 1500, QEasingCurve.OutCubic)

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
            self.windowOpacity(), 0.0, 1000, QEasingCurve.InCubic, on_finish=_on_faded
        )
