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

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QGraphicsScene, QGraphicsView, QSplitter, QSizePolicy, QSpacerItem, QProgressBar, QLabel, QFrame, QScrollArea, QGraphicsOpacityEffect, QSystemTrayIcon, QMenu, QDialog
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
from utils.pickers.PhrasePicker import motivationalMessages
from pretty_widgets.utils.settings import appName, set_nested, get_nested, set_value, get
from utils.helpers import ensure_dir, clean_pycache
from utils.persistence.session import session_path, enter_project, session_residue
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
        # PrettyEdit in proxy-less mode (parent_node=None).  Placeholder
        # picked fresh from the shared phrase bank each time the dialog
        # opens — every new project is announced with its own little
        # uplifting sample.
        from pretty_widgets.PrettyEdit import PrettyEdit
        from PySide6.QtGui import QFontMetrics as _QFM
        self._input = PrettyEdit(
            None,
            font_family    = Theme.healthFontFamily,
            font_size      = Theme.healthFontSizeLabel,
            font_color     = Theme.textPrimary,
            always_visible = True,
            enter_commits  = True,
            placeholder    = f"{random.choice(motivationalMessages)}\u2026",
        )
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 5px;
                padding: 6px 10px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
        """)
        # Single-line visual height — PrettyEdit is multi-line by nature but
        # enter_commits=True keeps it behaving like a line edit for input.
        _fm = _QFM(self._input.font())
        self._input.setFixedHeight(_fm.lineSpacing() + 14)
        self._input.committed.connect(lambda _t: self.accept())
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
        return self._input.toPlainText().strip()


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
        # Cross-session copy/paste — clipboard is a pure-Python dict that
        # survives scene teardowns because it holds zero Qt references.
        # Same dict shape as an .intricate session payload, consumed by
        # the existing Scene.import_session path (used by SessionNode
        # "Total Recall" drag-drop since v0.0.2 — paste is that same
        # path keyboard-triggered).
        self._node_clipboard_payload: dict | None = None
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_selected_chain)
        QShortcut(QKeySequence("Ctrl+V"), self, self._paste_node_chain)

        # The Companion — app-scoped ClaudeNode that follows the user across
        # sessions. One per app, excluded from session serialization, parked in
        # a persistent limbo scene during swaps and re-attached at the preferred
        # seat of the incoming session.
        #
        # Two protections are required for the transfer to survive intact:
        #
        # 1. Limbo scene. When the companion leaves the current scene, it must
        #    land somewhere — not scene()==None, or else BaseNode's scene-change
        #    demolition path fires. A persistent QGraphicsScene on the app is
        #    the "in between", held alive across the whole app lifetime.
        #
        # 2. _pinned_across_scenes flag. Qt's cross-scene move is NOT atomic —
        #    the item briefly sees scene()==None during the transfer (internally
        #    Qt does remove-then-add). BaseNode.itemChange honours the pin flag
        #    and skips _prepare_for_removal when it's set, so the companion's
        #    proxies, signals, and demolition crew don't wake up mid-flight.
        #
        # Conversation persistence is a later concern; for now only the seat
        # map persists via a sidecar file.
        from PySide6.QtWidgets import QGraphicsScene
        self._companion = None
        self._companion_limbo = QGraphicsScene(self)
        self._companion_seats: dict = self._load_companion_seats()

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

        # ── Titlebar InfoBar mirror ─────────────────────────────────────────
        # Same channel, different stage. When the bottom bar's InfoBar strip is
        # not visible (curtains rolled up, or splitter dragged to fully hide),
        # messages route here instead — with full personality preserved.
        # Idle state is blank opacity-zero; only lit during a whispered message.
        # Titlebar InfoBar font scales with the titlebar height so the two
        # stay visually proportional no matter what the user sets
        # handle_height_top to in settings.toml.  Reference: 9px font at
        # 25px handle — the ratio that felt right on 2026-04-18.  Floor at
        # 6px so the text stays legible if someone shrinks the handle.
        _INFO_FONT_RATIO = 9 / 25
        _info_font_px = max(6, round(Theme.handleHeightTop * _INFO_FONT_RATIO))
        self.info_label_top = pretty_label("", alignment=Qt.AlignCenter)
        self.info_label_top.setStyleSheet(
            f"background: transparent; border: none; padding: 0px 4px 0px 4px;"
            f" color: {Theme.textPrimary}; font-family: Chandler42; font-weight: 500; font-style: italic; font-size: {_info_font_px}px;"
        )
        self.info_label_top.setParent(self.top_toolbar)
        self._info_opacity_top = QGraphicsOpacityEffect()
        self._info_opacity_top.setOpacity(0.0)
        self.info_label_top.setGraphicsEffect(self._info_opacity_top)

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

        # Titlebar InfoBar — occupies the central dead zone between the
        # curtains/project-selector cluster on the left and the tray/max/exit
        # cluster on the right. Width flexes with window width; height is a
        # comfortable 24px strip sitting vertically centered in the toolbar.
        if hasattr(self, 'info_label_top'):
            left_edge  = Theme.toolbarCurtainsX + (
                self._curtains_btn.width() if hasattr(self, '_curtains_btn') else 0
            ) + gap * 4
            right_edge = (
                self._tray_btn.x() if hasattr(self, '_tray_btn') else ex
            ) - gap * 4
            width  = max(60, right_edge - left_edge)
            height = 24
            iy = (tb.height() - height) // 2
            self.info_label_top.setGeometry(left_edge, iy, width, height)
            self.info_label_top.raise_()

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

    # Leave a small margin at the bottom when maximising so the Windows
    # auto-hide taskbar's cursor-at-edge trigger zone stays reachable.
    # Intricate is always-on-top and would otherwise overlay that 1-2px
    # trigger band — a 5px gap gives the cursor a reliable runway without
    # sacrificing any meaningful canvas real estate.
    _TASKBAR_TRIGGER_MARGIN = 5

    def toggle_fullscreen(self):
        screen = self.screen().geometry()
        target = screen.adjusted(0, 0, 0, -self._TASKBAR_TRIGGER_MARGIN)
        if self.geometry() == target:
            # Already filling the reserved area — restore
            if hasattr(self, '_pre_fullscreen_geometry'):
                self.setGeometry(self._pre_fullscreen_geometry)
            self._is_fullscreen = False
        else:
            # Not filling — maximize into the reserved area
            self._pre_fullscreen_geometry = self.geometry()
            self.setGeometry(target)
            self._is_fullscreen = True

    # =========================================================================
    # Toolbar context menu — hidden unlock/lock for folder management
    # =========================================================================

    _folders_unlocked = False

    def _make_exid_button(self, text: str, clicked=None, tooltip: str = "",
                           left_padding: int = 4) -> QPushButton:
        """Create + place a staging-area ("eXid") utility button in the
        bottom toolbar's right group. Encapsulates the canonical test-bench
        styling (16pt font, Theme.buttonBg, 6px radius, HoverGlow install,
        font-metric width plus Reey-overshoot padding) and wakes up the
        buttons_row if the bench was dormant.

        Args:
            text: button label (used for both caption and width-from-metrics)
            clicked: slot connected to clicked signal
            tooltip: tooltip text
            left_padding: interior left padding — tune up to ~14 for Reey
                glyphs that extend beyond QFontMetrics.horizontalAdvance()

        Returns:
            The button, already placed in the right_layout. Caller can keep
            a reference (e.g. for install_tooltip or later removal) but
            doesn't need to call addWidget.
        """
        from PySide6.QtGui import QFontMetrics
        from utils.motion.hover_glow import HoverGlow

        btn = button(text, clicked=clicked)
        btn.setMinimumSize(0, 0)
        if tooltip:
            btn.setToolTip(tooltip)

        font = btn.font()
        font.setPointSize(16)
        btn.setFont(font)

        # Width: label's font-metric advance + generous Reey overshoot so
        # glyphs that extend beyond the advance (common on Reey faces)
        # don't clip.
        fm = QFontMetrics(font)
        btn.setFixedWidth(fm.horizontalAdvance(text) + 32)
        btn.setMinimumHeight(fm.height() + 6 + 18)

        base_style = (
            f"QPushButton {{ background-color: {Theme.buttonBg};"
            f" border: none; border-radius: 6px;"
            f" padding: 6px 2px 18px {left_padding}px; }}"
        )
        HoverGlow.install(btn, base_style)

        # Place the button and wake the bench up. The dormant-state hide
        # at init gets reversed the moment any candidate lands here.
        self._exid_right_layout.addWidget(btn)
        if hasattr(self, 'buttons_row'):
            self.buttons_row.show()
        return btn

    def _show_toolbar_context_menu(self, global_pos) -> None:
        """Right-click the top toolbar — graduated utilities (restore last
        deleted node, snip a wire), project folder lock, media cache refresh,
        audio mute toggle, polaroid viewport snapshot.

        The top group is registry-driven from the "titlebar" action category
        in node_registry.toml — promotions from the sidebar land there by
        flipping the entry's ``category`` field, no wiring change needed.
        """
        from utils.persistence import registry

        self._ensure_dispatch()
        menu = self._styled_menu()

        # ── Registry-driven utilities (graduated from the sidebar) ─────────
        titlebar_actions = registry.get_actions_by_category("titlebar")
        for key, entry in titlebar_actions:
            icon_attr = entry.get("icon", "")
            fallback  = entry.get("icon_fallback", "#6b5a47")
            icon_val  = getattr(Theme, icon_attr, None)
            pix = Theme.icon(icon_val, fallback_color=fallback) if icon_val else Theme.icon(None)
            act = menu.addAction(QIcon(pix), entry.get("name", key))
            tip = entry.get("tooltip", "")
            if tip:
                act.setToolTip(tip)
            handler = self._action_dispatch.get(key)
            if handler:
                act.triggered.connect(handler)
        if titlebar_actions:
            menu.addSeparator()

        if self._folders_unlocked:
            act = menu.addAction("Lock Folders")
            act.setToolTip("Re-acquire working directory lock on the active project")
            act.triggered.connect(self._lock_folders)
        else:
            act = menu.addAction("Unlock Folders")
            act.setToolTip("Release directory locks so folders can be deleted in Explorer")
            act.triggered.connect(self._unlock_folders)
        menu.addSeparator()
        refresh = menu.addAction("Refresh Media Cache")
        refresh.setToolTip("Purge the project's media cache and re-ingest from sources (images + videos)")
        refresh.triggered.connect(self._refresh_media_cache)

        menu.addSeparator()
        from utils.audio import audio
        if audio.is_muted():
            mute_act = menu.addAction("Unmute")
            mute_act.setToolTip("Restore audio — chimes, video nodes, audio nodes fade back in")
        else:
            mute_act = menu.addAction("Mute")
            mute_act.setToolTip("Silence all audio — chimes and every video / audio node")
        mute_act.triggered.connect(self._toggle_global_mute)

        snap = menu.addAction("Polaroid Snapshot")
        snap.setToolTip("Capture the current viewport with transparent background (alpha)")
        snap.triggered.connect(self._snapshot_viewport)

        menu.exec(global_pos)

    def _refresh_media_cache(self) -> None:
        """Purge the project media cache and re-ingest from every live media node.

        Unified over images and videos. Nodes with a valid source_path re-read
        the source; nodes without fall back to whatever in-memory form they hold.
        Drift (pre-refresh cache_key disagreeing with live source hash) is counted
        per-type so the user sees which sources changed.
        """
        from nodes.ImageNode import ImageNode
        from nodes.VideoNode import VideoNode
        from utils.persistence.media_cache import (
            cache_dir, cache_pixmap, cache_source_file, hash_file, key_hash,
        )

        from send2trash import send2trash
        removed = 0
        for f in cache_dir().iterdir():
            if not f.is_file():
                continue
            try:
                send2trash(str(f))
                removed += 1
            except OSError:
                pass

        # ── Images ─────────────────────────────────────────────────────────
        img_regen = img_reload = img_drift = 0
        for item in list(self.scene.items()):
            if not isinstance(item, ImageNode):
                continue
            src = item.data.source_path
            if src and Path(src).exists():
                sp = Path(src)
                if item.data.cache_key:
                    src_hash = hash_file(sp)
                    if src_hash and src_hash != key_hash(item.data.cache_key):
                        img_drift += 1
                        logger.info("[cache] image drift — %s", sp.name)
                item.data.cache_key = ""
                item.load_from_path(src)
                img_reload += 1
            elif item._pixmap and not item._pixmap.isNull():
                item.data.cache_key = cache_pixmap(item._pixmap)
                img_regen += 1

        # ── Videos ─────────────────────────────────────────────────────────
        vid_reload = vid_drift = 0
        for item in list(self.scene.items()):
            if not isinstance(item, VideoNode):
                continue
            src = item.data.source_path
            if src and Path(src).exists():
                sp = Path(src)
                if item.data.cache_key:
                    src_hash = hash_file(sp)
                    if src_hash and src_hash != key_hash(item.data.cache_key):
                        vid_drift += 1
                        logger.info("[cache] video drift — %s", sp.name)
                # Re-ingest synchronously here (we're inside an explicit user
                # refresh — worth the wait to know it landed).
                new_key = cache_source_file(sp)
                if new_key:
                    item.data.cache_key = new_key
                    try:
                        st = sp.stat()
                        item.data.source_size  = st.st_size
                        item.data.source_mtime = st.st_mtime
                    except OSError:
                        pass
                vid_reload += 1

        total = img_reload + img_regen + vid_reload
        drift_total = img_drift + vid_drift
        logger.info(
            "[cache] refresh — purged %d; images: %d reloaded, %d re-cached, %d drifted; videos: %d reloaded, %d drifted",
            removed, img_reload, img_regen, img_drift, vid_reload, vid_drift,
        )
        msg = f"Media cache refreshed — {total} item(s)"
        if drift_total:
            msg += f" ({drift_total} had drifted)"
        self.show_info(msg)

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
            from utils.persistence.session import project_root_from_session
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
            # ③ Delay-hide so the bottom toolbar stays visible for the first
            # 2/3 of the roll — gives the window "visual weight", like the
            # thickness is physically pulling up rather than just shrinking.
            # Scales with timing so the ratio holds at any slider value.
            hide_delay = max(1, int(Theme.windowRollTimingUp * 2 / 3))
            QTimer.singleShot(hide_delay, self._sidebar_splitter.hide)
            if self.scene:
                self.scene.pause_all_videos()
            self._last_docked_exe = ""
            self._dock_watcher.start()
            self._start_meov()
        else:
            self._dock_watcher.stop()
            # Defensive belt — a dock_anim (from _check_window_behind) can
            # still be in flight when expand fires; left running, it fights
            # the curtain_anim over the same `geometry` property. Stop it
            # explicitly so the expand animation owns the channel.
            if hasattr(self, '_dock_anim') and self._dock_anim is not None:
                try:
                    self._dock_anim.stop()
                except RuntimeError:
                    pass  # anim was already torn down
            self._stop_meov()

            # Fivefold display-resolution validation before using Qt's
            # availableGeometry (which shrinks to shell work-area
            # reservations — the 2026-04-22 curtains bug). If all five
            # independent readers agree, use their physical resolution and
            # subtract the taskbar ourselves via SHAppBarMessage, bypassing
            # the work-area layer entirely. On any disagreement: log every
            # layer's reading and fall back to availableGeometry (the
            # known-behaviour baseline).
            from utils import display_resolution
            reading = display_resolution.authoritative_resolution()
            screen = self.screen()
            screen_geom = screen.geometry()

            if reading.agreed and (
                reading.consensus_value == (screen_geom.width(), screen_geom.height())
            ):
                # Five layers agree AND Qt's own monitor geometry matches
                # — trust the physical rect, subtract taskbar by direct
                # query (not by work-area math).
                tb_h = display_resolution.taskbar_height_on_bottom_of(
                    screen_geom.top(), screen_geom.bottom(),
                    screen_geom.left(), screen_geom.right(),
                )
                avail_top = screen_geom.top()
                effective_bottom = screen_geom.bottom() - tb_h - self._TASKBAR_TRIGGER_MARGIN
                source_tag = "consensus"
            else:
                # Fall back to the baseline Qt path — what the code has
                # always done. Safe default while consensus is unreachable
                # (post driver botch, CRU-scaled resolution vs raw EDID,
                # etc.).
                avail = screen.availableGeometry()
                avail_top = avail.top()
                effective_bottom = avail.bottom() - self._TASKBAR_TRIGGER_MARGIN
                source_tag = "fallback"

            max_height = effective_bottom - avail_top + 1
            height = min(self.original_height, max_height)
            y = min(start_rect.y(), effective_bottom - height + 1)
            y = max(avail_top, y)
            end_rect = QRect(start_rect.x(), y,
                             start_rect.width(), height)

            # Single forensic log per expand — captures everything about
            # the decision so the next curtain weirdness has full context.
            full = screen_geom
            avail_q = screen.availableGeometry()
            logger.debug(
                "[curtains] expand source=%s | screen=%s full=%s avail_qt=%s "
                "reserved_by_qt=%dpx | 5-layer: %s | original_h=%d max_h=%d → end=%s",
                source_tag,
                screen.name(),
                (full.x(), full.y(), full.width(), full.height()),
                (avail_q.x(), avail_q.y(), avail_q.width(), avail_q.height()),
                full.height() - avail_q.height(),
                reading.summary(),
                self.original_height,
                max_height,
                (end_rect.x(), end_rect.y(), end_rect.width(), end_rect.height()),
            )

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

    # Info bar row height — the "minimal" snap target. Matches the fixed height
    # set on _info_bar_row in _setupBottomToolbar.
    _INFO_BAR_STRIP_H = 28

    def _on_v_splitter_moved(self, _pos: int, _index: int) -> None:
        """Persist bottom toolbar height whenever the vertical splitter moves.

        Also enforces two magnet-snap detents as the user drags the handle near
        the bottom of the panel: snap to 0 (fully hidden) or to the InfoBar
        strip height (minimal mode, only the whisper bar visible). Above the
        snap zone the handle drags freely.
        """
        # Guard against the snap itself triggering recursive signals
        if getattr(self, '_snap_guard', False):
            return

        sizes = self._v_splitter.sizes()
        if len(sizes) != 2:
            return

        bottom = sizes[1]
        strip  = self._INFO_BAR_STRIP_H
        # Snap thresholds: below strip/2 → 0, below strip*1.5 → strip, else free
        snap_to = None
        if 0 < bottom < strip // 2:
            snap_to = 0
        elif strip // 2 <= bottom < int(strip * 1.5):
            snap_to = strip

        if snap_to is not None and snap_to != bottom:
            self._snap_guard = True
            total = sizes[0] + sizes[1]
            self._v_splitter.setSizes([total - snap_to, snap_to])
            self._snap_guard = False
            bottom = snap_to

        set_value("ui", "bottom_height", bottom)

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._preview_pinned = pinned
        self._pin_btn.setText("●" if pinned else "○")
        if not pinned:
            # Re-evaluate immediately so deselecting clears stale preview
            self._on_selection_changed()
        if pinned and self._preview_pixmap:
            # Persist which image is pinned so it survives a restart.
            # Caption goes along so the restore doesn't need the source
            # ImageNode to be in the scene to recover it.
            set_value("ui", "preview_pinned", True)
            set_value("ui", "preview_pinned_path", self._pinned_source_path or "")
            set_value("ui", "preview_pinned_caption", self._preview_caption.text())
        else:
            set_value("ui", "preview_pinned", False)
            set_value("ui", "preview_pinned_path", "")
            set_value("ui", "preview_pinned_caption", "")

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
        """Select all nodes connected to the current selection via wires.
        Duck-typed over BaseNode + StickerNode roots — stickers have
        `connections = []` forever, so they contribute nothing to the
        walk, but accepting them as seeds keeps the API uniform."""
        seeds = [item for item in self.scene.selectedItems()
                 if hasattr(item, 'connections')]
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
            if hasattr(node, 'connections') and id(node) in visited:
                node.setSelected(True)

    # =========================================================================
    # Cross-session copy / paste — undo-cache-in-the-recycle-bin pattern
    # =========================================================================
    # The historic bug that killed both Intricate and Notepad++ Duplex+ Turbo
    # (and led to the full-repo delete + handwritten 2k core rewrite) lived
    # at the node/session boundary: clipboards that held live Qt objects
    # couldn't survive session teardown. The fix is architectural — the
    # clipboard is a pure Python dict, identical in shape to an .intricate
    # session payload. Session switch purges the scene's Qt tree; the dict
    # in self._node_clipboard_payload doesn't care because it holds zero
    # Qt references. Paste funnels back through Scene.import_session — the
    # SessionNode "Total Recall" drag-drop path that's been battle-tested
    # since v0.0.2 — with a fresh UUID remap so there's never a collision.

    def _copy_selected_chain(self) -> None:
        """Ctrl+C — capture the selected chain as a session-payload dict.

        BFS walks the selection's connected component, serializes every
        node via to_dict, and emits connections only where BOTH endpoints
        are in the captured set (no dangling refs ever reach paste).
        The payload is stored on self as a plain dict — pure data,
        indestructible from Qt's perspective.
        """
        from collections import Counter
        seeds = [item for item in self.scene.selectedItems()
                 if hasattr(item, 'connections') and hasattr(item, 'to_dict')]
        logger.log(5, "[clipboard] copy begin — %d seeds in selection (%d total selected)",
                   len(seeds), len(self.scene.selectedItems()))
        if not seeds:
            return
        visited_ids: set = set()
        captured: list = []
        queue = list(seeds)
        while queue:
            node = queue.pop(0)
            nid = id(node)
            if nid in visited_ids:
                continue
            visited_ids.add(nid)
            captured.append(node)
            # Guard the neighbour walk — if a node's C++ side is torn down
            # mid-BFS, .connections or .start_node could raise RuntimeError.
            # Silent crash here would drop every later node in the queue,
            # which manifests as "the clipboard randomly loses half the chain".
            try:
                conns = list(node.connections)
            except (RuntimeError, AttributeError):
                conns = []
            for conn in conns:
                try:
                    sn = conn.start_node
                    en = conn.end_node
                except (RuntimeError, AttributeError):
                    continue
                for neighbour in (sn, en):
                    if neighbour and neighbour is not node and id(neighbour) not in visited_ids:
                        queue.append(neighbour)

        cap_types = Counter(type(n).__name__ for n in captured)
        logger.log(5, "[clipboard] captured %d nodes by BFS: %s",
                   len(captured), dict(cap_types))

        # Serialize nodes — per-node try/except so one broken to_dict
        # doesn't poison the whole copy
        node_dicts: list = []
        dropped_types: list = []
        for n in captured:
            try:
                d = n.to_dict()
            except Exception:
                logger.exception("[clipboard] to_dict raised on %s", type(n).__name__)
                dropped_types.append((type(n).__name__, "exception"))
                continue
            if not d:
                logger.warning("[clipboard] %s.to_dict returned falsy", type(n).__name__)
                dropped_types.append((type(n).__name__, "falsy"))
                continue
            if not d.get("uuid"):
                logger.warning("[clipboard] %s.to_dict missing uuid; node_type=%r",
                               type(n).__name__, d.get("node_type"))
                dropped_types.append((type(n).__name__, "no-uuid"))
                continue
            node_dicts.append(d)

        if dropped_types:
            logger.warning("[clipboard] dropped %d node(s) during serialize: %s",
                           len(dropped_types), dropped_types)
        emit_types = Counter(d.get("node_type", "?") for d in node_dicts)
        logger.log(5, "[clipboard] serialized %d/%d nodes by node_type: %s",
                   len(node_dicts), len(captured), dict(emit_types))

        # Serialize connections — only where BOTH endpoints are captured
        captured_uuids = {d.get("uuid") for d in node_dicts if d.get("uuid")}
        seen_conn_ids: set = set()
        conn_dicts: list = []
        for n in captured:
            for conn in n.connections:
                cid = id(conn)
                if cid in seen_conn_ids:
                    continue
                seen_conn_ids.add(cid)
                if conn.start_node is None or conn.end_node is None:
                    continue
                try:
                    su = conn.start_node.data.uuid
                    eu = conn.end_node.data.uuid
                except Exception:
                    continue
                if su in captured_uuids and eu in captured_uuids:
                    conn_dicts.append({"start_uuid": su, "end_uuid": eu})

        self._node_clipboard_payload = {
            "nodes":       node_dicts,
            "connections": conn_dicts,
        }
        n_count = len(node_dicts)
        w_count = len(conn_dicts)
        pieces = f"{n_count} node{'s' if n_count != 1 else ''}"
        if w_count:
            pieces += f" + {w_count} wire{'s' if w_count != 1 else ''}"
        self.show_info(f"Copied {pieces}")

    def _paste_node_chain(self) -> None:
        """Ctrl+V — spawn the clipboard payload into the current session.

        Delegates to Scene.import_session which handles fresh-UUID remap,
        position offsetting relative to the viewport centre, and wire
        reconstruction. Non-destructive: pasting twice spawns two
        independent copies. Silently no-ops on empty clipboard or if
        the view isn't ready yet.
        """
        payload = getattr(self, '_node_clipboard_payload', None)
        if not payload or not payload.get("nodes"):
            return
        try:
            anchor = self.view.mapToScene(self.view.viewport().rect().center())
        except Exception:
            return
        try:
            created = self.scene.import_session(payload, anchor=anchor)
        except Exception:
            logger.exception("[clipboard] paste failed")
            return

        # Auto-select the pasted chain so the user can drag the whole chunk
        # to a nice place without the extra Ctrl+A click — mirrors the
        # SessionNode "Total Recall" drag-drop behaviour.
        if created:
            self.scene.clearSelection()
            for node in created:
                try:
                    node.setSelected(True)
                except RuntimeError:
                    pass  # node may have been removed during import

        count = len(created)
        self.show_info(f"Pasted {count} node{'s' if count != 1 else ''}")

    def import_intricate_file(self, path: str) -> int:
        """Read a session file from disk and spawn its chain into the
        currently loaded scene. Shared entry point for:
          - Command-line: `python main.py file.intricate`
          - Double-click in Windows Explorer (via file association +
            singleton IPC from shared_braincell.send_command)
          - Any future File menu / drag-drop shortcut

        Behaviourally mirrors the SessionNode "Total Recall" drag-drop
        and Ctrl+V paste paths — chain anchors at the current viewport
        centre, newly-created nodes are auto-selected so they move as
        one chunk. Returns the count of nodes actually created.
        """
        from utils.persistence.session import SessionManager
        fname = Path(path).name
        try:
            payload = SessionManager.get_session_data(path)
        except Exception:
            logger.exception("[import] failed to parse session file: %s", path)
            self.show_info(f"Couldn't parse {fname}")
            return 0
        if not payload or not payload.get("nodes"):
            self.show_info(f"No nodes found in {fname}")
            return 0

        try:
            anchor = self.view.mapToScene(self.view.viewport().rect().center())
        except Exception:
            logger.exception("[import] view not ready for file: %s", path)
            return 0

        try:
            created = self.scene.import_session(payload, anchor=anchor)
        except Exception:
            logger.exception("[import] import_session failed for %s", path)
            return 0

        if created:
            self.scene.clearSelection()
            for node in created:
                try:
                    node.setSelected(True)
                except RuntimeError:
                    pass

        n = len(created)
        self.show_info(f"Imported {n} node{'s' if n != 1 else ''} from {fname}")
        return n

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
        """After session load: re-pin the previously pinned image.

        Primary path finds a matching ImageNode in the current scene so
        the caption / dims mirror the live node. If that fails — because
        the pinned image lives in a different session than the one just
        loaded, the ImageNode's async pixmap load hasn't completed yet,
        or the node has been deleted since the pin was set — falls back
        to loading the pixmap directly from the stored source_path using
        the saved caption. Together these two paths make the pin survive
        both session switches and app restarts.
        """
        if not get("ui", "preview_pinned", False):
            return
        saved_path = get("ui", "preview_pinned_path", "")
        if not saved_path:
            return

        # Primary: matching ImageNode in current scene (live node → live pixmap)
        for item in self.scene.items():
            if isinstance(item, ImageNode) and item._pixmap and not item._pixmap.isNull():
                if item.data.source_path == saved_path:
                    self._show_node_preview(item)
                    self._set_pin_active(True)
                    return

        # Fallback: load directly from source_path on disk
        p = Path(saved_path)
        if p.is_file():
            px = QPixmap(str(p))
            if not px.isNull():
                saved_caption = get("ui", "preview_pinned_caption", "")
                self._pinned_source_path = saved_path
                self._update_preview(
                    px,
                    saved_caption,
                    f"{px.width()} × {px.height()}",
                )
                self._set_pin_active(True)
        # If the file is gone, pin silently drops — user can re-pin from
        # a new image. We deliberately don't clear the saved settings
        # here so a temporarily-unmounted drive (e.g. external media)
        # can restore the pin when it comes back.

    def _set_pin_active(self, active: bool) -> None:
        """Apply pin state + button glyph without triggering _on_pin_toggled's
        settings save. Used by _restore_pinned_preview after the pinned
        image is already loaded into the panel via its own path."""
        self._preview_pinned = active
        self._pin_btn.blockSignals(True)
        self._pin_btn.setChecked(active)
        self._pin_btn.setText("●" if active else "○")
        self._pin_btn.blockSignals(False)

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

        def _cat_btn(icon_name, tooltip, menu_fn, scale=None):
            """Category button — icon fills the entire button, no Qt frame overhead.

            Sidebar icons (cream-on-transparent line art inside a ring) have
            ~22% transparent padding baked into the PNG, so a button at
            setIconSize(sz, sz) renders with ~6-7px of dead whitespace on
            every edge. That dead space dominates the visible gap between
            stacked buttons — sidebarButtonGap looks neutralised no matter
            what value it holds. The default 1.28× scale (matches
            NodeButton.py:137) inflates the icon rect so the glyph content
            reaches the button's edges; after this, sidebarButtonGap is
            the ONLY contributor to the visible gap.

            The optional `scale` kwarg overrides the family default for
            icons whose fill ratio differs — e.g. the Anthropic logo has
            closer to 100% fill, so it needs scale=1.0 (or less) to avoid
            clipping the sidebar edge while still reading comparable in
            visual size to the circular family. Future: per-family fill
            ratios in [theme.sidebar].
            """
            sz = Theme.iconButtonSize
            effective_scale = scale if scale is not None else Theme.sidebarIconScale
            ico_sz = int(sz * effective_scale)
            b = button(icon_name=icon_name, tooltip=tooltip)
            b.setFixedSize(sz, sz)
            b.setIconSize(QSize(ico_sz, ico_sz))
            b.setFlat(True)
            b.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")
            def _on_click(_=None, btn=b, fn=menu_fn, label=tooltip):
                logger.log(5, "[sidebar] category click → %s", label)
                fn(btn)
            b.clicked.connect(_on_click)
            install_tooltip(b)
            layout.addWidget(b, alignment=Qt.AlignHCenter)

        _cat_btn(Theme.iconText,        "Text",   self._show_text_menu)
        _cat_btn(Theme.iconImagesGroup,  "Images", self._show_images_menu)
        _cat_btn(Theme.iconAudioGroup,   "Audio",  self._show_audio_menu)
        _cat_btn(Theme.iconVisualGroup,  "Visual", self._show_visual_menu)
        _cat_btn(Theme.iconHealthGroup,  "Health", self._show_health_menu)
        _cat_btn(Theme.iconToolsGroup,   "Tools",  self._show_tools_menu)
        _cat_btn(Theme.iconInfoGroup,    "Info",   self._show_info_menu)
        # Anthropic logo fills its bounding box closer to 100% than the
        # circular family, so scale=1.0 keeps it visually comparable in
        # size to the circular icons without clipping the sidebar edge.
        _cat_btn(Theme.iconAnthropic,    "Claude", self._show_claude_menu, scale=1.0)

        # ── Sliders row (top) + progress-bars row (bottom) ───────────────────
        # No explicit stretch — sliders_row carries the Expanding vertical
        # sizePolicy so IT absorbs the gap between the last category button
        # and the progress-bars row. At max value, the slider handle reaches
        # up to just under the button row, matching the layout intent.
        # Target layout is 3 sticker sliders above, 3 pink progress bars below.
        # Each row is a 3-column grid at sz // 3 per column so columns align
        # vertically between the two rows. Current population:
        #   sliders row   → blur (col 1), zoom (col 2), reserved (col 3)
        #   progress row  → reserved (col 1), reserved (col 2), joy (col 3)
        # Reserved slots use fixed-size spacers so column alignment is
        # preserved before the future peers land.
        import pretty_widgets.utils.settings as _s
        sz = Theme.iconButtonSize
        bar_width = sz // 3
        bar_min_height = sz * 2

        def _reserved_slot():
            return QSpacerItem(
                bar_width, bar_min_height,
                QSizePolicy.Fixed, QSizePolicy.Fixed,
            )

        # ── Sliders row ──────────────────────────────────────────────────────
        sliders_row = QWidget()
        sliders_row.setStyleSheet("background: transparent;")
        # Expanding vertical so this row absorbs all vertical slack between
        # the top category buttons and the progress-bars row below — the
        # sliders inside inherit the space and their handles travel to the
        # full physical extent rather than being pinned at bar_min_height.
        sliders_row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sliders_row_layout = QHBoxLayout(sliders_row)
        sliders_row_layout.setContentsMargins(0, 0, 0, 0)
        sliders_row_layout.setSpacing(0)
        sliders_row_layout.setAlignment(Qt.AlignHCenter)

        # Blur slider — drives the backdrop opacity layer (was called fog;
        # renamed because it's actually the blur transparency level).
        _blur_init = int(_s.get_nested("intricate", "canvas", "blur_alpha", 180))
        self.blur_slider = pretty_slider(
            Qt.Vertical,
            handle_icon="slider_handle_vertical.png",
            handle_size=28,
            range=(0, 255),
            value=_blur_init,
            invertedAppearance=False,
            fixedWidth=bar_width,
            minimumHeight=bar_min_height,
            valueChanged=self._on_blur_slider_changed,
        )
        # No alignment flag — a Qt alignment on addWidget disables expansion,
        # so the slider would stay pinned at minimumHeight. Letting it fill
        # the row is the whole point of the Expanding sizePolicy above.
        sliders_row_layout.addWidget(self.blur_slider)

        # Zoom slider — moved from the bottom toolbar to live with its peers.
        self._zoom_slider = pretty_slider(
            Qt.Vertical,
            handle_icon="slider_handle_vertical.png",
            handle_size=28,
            range=(3, 500),
            value=100,
            invertedAppearance=False,
            fixedWidth=bar_width,
            minimumHeight=bar_min_height,
            singleStep=5,
            pageStep=25,
            valueChanged=self._on_zoom_slider,
        )
        sliders_row_layout.addWidget(self._zoom_slider)

        # Reserved column for a future 3rd slider
        sliders_row_layout.addSpacerItem(_reserved_slot())

        # No alignment on the outer addWidget either — same reason. The
        # inner sliders_row_layout already handles horizontal centering
        # via its setAlignment(Qt.AlignHCenter) on the QHBoxLayout.
        layout.addWidget(sliders_row)
        layout.addSpacing(2)

        # ── Progress-bars row ────────────────────────────────────────────────
        progress_bars_row = QWidget()
        progress_bars_row.setStyleSheet("background: transparent;")
        progress_bars_row_layout = QHBoxLayout(progress_bars_row)
        progress_bars_row_layout.setContentsMargins(0, 0, 0, 0)
        progress_bars_row_layout.setSpacing(0)
        progress_bars_row_layout.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)

        # Reserved columns for the two future progress bars
        progress_bars_row_layout.addSpacerItem(_reserved_slot())
        progress_bars_row_layout.addSpacerItem(_reserved_slot())

        # Joy bar — hunger/mood indicator, rises on feed, drains on time.
        self.joy_bar = QProgressBar()
        self.joy_bar.setOrientation(Qt.Vertical)
        self.joy_bar.setRange(0, 100)
        self.joy_bar.setValue(int(_s.get_nested("intricate", "joy", "bar_value", 100)))
        self.joy_bar.setTextVisible(False)
        self.joy_bar.setFixedWidth(bar_width)
        self.joy_bar.setMinimumHeight(bar_min_height)
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
        progress_bars_row_layout.addWidget(self.joy_bar, alignment=Qt.AlignBottom)

        layout.addWidget(progress_bars_row, alignment=Qt.AlignHCenter)
        layout.addSpacing(4)

        # ── Joy bucket — own bottom-anchored container (feed + sleep) ────────
        # The joy bar moved up into the bars_row; this container now holds
        # only the feed button and sleep toggle.
        joy_container = QWidget()
        joy_container.setStyleSheet("background-color: transparent;")
        joy_layout = QVBoxLayout(joy_container)
        joy_layout.setContentsMargins(0, 0, 0, 0)
        joy_layout.setSpacing(0)
        joy_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

        # Feed button — dynamic radial shadow, physical press depth
        from utils.ShadowStickerButton import ShadowStickerButton
        clean_pix = Theme.icon(Theme.iconCatnipFeedClean, fallback_color="#d87a9e")
        self._feed_btn = ShadowStickerButton(clean_pix, sz, parent=joy_container)
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
        # Awake-state sticker — trio of hearts in the upper-left, echoing the
        # Thingaling heart above; at 24px it reads as a quiet corner accent.
        # The paired sleeping-state sticker (purple sleep mask) is swapped in
        # by _sleep_joy when the joy system goes to sleep.
        self._sleep_btn.setIcon(QIcon(Theme.icon(Theme.iconAwakeIconic, fallback_color="#d87a9e")))
        self._sleep_btn.setIconSize(QSize(24, 24))
        self._sleep_btn.setToolTip("Tuck me in")
        install_tooltip(self._sleep_btn)
        joy_layout.addWidget(self._sleep_btn, alignment=Qt.AlignHCenter)

        layout.addWidget(joy_container)

        # ── Joy bucket counter ─────────────────────────────────────────────
        # Bucket count has its own tiny file store (utils/joy_buckets.py) —
        # detached from settings.toml so the value can be tweaked by hand
        # without touching the shared-braincell config surface. A watcher
        # picks up external edits live so hand-tweaks don't get clobbered
        # by the next _persist_happy tick.
        import pretty_widgets.utils.settings as _s
        from utils import joy_buckets
        self._joy_bucket_count = joy_buckets.get_buckets()
        self._joy_buckets_watcher = joy_buckets.JoyBucketsWatcher(self)
        self._joy_buckets_watcher.changed.connect(self._on_joy_buckets_external_change)
        self._joy_happy_secs   = float(_s.get_nested("intricate", "joy", "happy_secs", 0.0))
        self._joy_bucket_label = pretty_label(
            str(self._joy_bucket_count),
            alignment=Qt.AlignCenter,
        )
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())
        install_tooltip(self._joy_bucket_label)
        # Pink variable-number colour (Settlers convention) + Nabana emphasis
        # font (project-selector family) — the counter is a live value, so
        # it gets the same visual treatment as other variable numerics.
        self._joy_bucket_label.setStyleSheet(
            "color: #ffb6c1;"
            " font-family: 'My Olivin (Nabana)';"
            " font-size: 10pt;"
        )
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

    def _on_blur_slider_changed(self, value: int) -> None:
        """Drive canvas blur transparency and persist to settings.

        Guarded against self.view not existing — same early-sidebar reason
        as _on_zoom_slider. Setting the slider's initial value fires this
        once before the view lands.
        """
        if not hasattr(self, 'view'):
            return
        self.view._blur_alpha = value
        self.view.viewport().update()
        import pretty_widgets.utils.settings as _s
        _s.set_nested("intricate", "canvas", "blur_alpha", value)

    def _on_feed_pressed(self) -> None:
        """Mouse down — ShadowStickerButton handles the depth shift visually."""
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
        self._sleep_btn.setIcon(QIcon(Theme.icon(Theme.iconSleepingIconic, fallback_color="#9a7abf")))
        self._sleep_btn.setToolTip("Wake me up")

    def _wake_joy(self) -> None:
        """Exit sleep mode — normal depletion resumes."""
        if not self._joy_sleeping:
            return
        self._joy_sleeping = False
        self._joy_timer.setInterval(self._JOY_AWAKE_INTERVAL)
        self._joy_timer.start()          # restart with new interval
        self._sleep_btn.setText("")
        self._sleep_btn.setIcon(QIcon(Theme.icon(Theme.iconAwakeIconic, fallback_color="#d87a9e")))
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
            # Bump via the store so the file is the authoritative source
            # (no in-memory drift from any concurrent external edits).
            self._joy_bucket_count = joy_buckets.bump_buckets(1)
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
        """Save happy accumulator and bar value. Bucket count is NOT written
        here — it's persisted at earn time via joy_buckets.bump_buckets, so
        the file store is always authoritative and external hand-edits are
        never overwritten by a later _persist_happy tick."""
        import pretty_widgets.utils.settings as _s
        _s.set_nested("intricate", "joy", "happy_secs", round(self._joy_happy_secs, 1))
        _s.set_nested("intricate", "joy", "bar_value", self.joy_bar.value())

    def _on_joy_buckets_external_change(self, new_value: int) -> None:
        """Fired when joy_buckets.txt is edited from outside the running
        process (e.g., hand-tweak from a chat session). Sync the in-memory
        count and the label so the UI reflects the new value immediately."""
        self._joy_bucket_count = new_value
        self._joy_bucket_label.setText(str(new_value))
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())

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
            self._start_meov()

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
    # NODE SPAWN ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _viewport_spawn_anchor(self):
        """Preferred first-try position for sidebar-spawned nodes, in scene
        coordinates.  Biased to the upper-left quadrant of the current
        viewport (C3 on a 12×12 grid ≈ 25% from left, 25% from top).

        Rationale: the user's focus is usually somewhere around the
        viewport centre, and dropping a fresh node on top of that focus
        is disruptive.  Landing upper-left keeps the new node clearly
        visible while leaving the focus area intact.  Contrasts with
        chain-spawns (MarkdownNode split, WarmNode paste-split) which
        bias toward the right following reading direction."""
        vp = self.view.viewport()
        return self.view.mapToScene(vp.width() // 4, vp.height() // 4)

    def _spawn(self, add_fn, status_msg: str, **kwargs):
        """Create a node via *add_fn* and place it at the upper-left spawn
        anchor, falling through to scatter if that spot is occupied.

        Singleton factories (HealthNode, PerfNode, GitNode) return the
        existing instance when one already exists.  We detect that case
        by snapshotting the scene's item set before calling the factory:
        if the returned node was ALREADY in that set, the factory
        handed us back an existing node rather than creating a new one.
        Positional detection (comparing to the off-screen sentinel) was
        unreliable because some factories recenter the incoming pos
        (e.g. add_log_node subtracts half the rect), so the sentinel
        didn't round-trip unchanged.

        The factory is called with an off-screen position so spiral_place
        can measure the node's rect without collision artefacts, then the
        final position is applied.  Same pattern WarmNode's paste-split
        and MarkdownNode's auto-split use for chain-spawning."""
        from PySide6.QtCore import QPointF
        from utils.placement import spiral_place

        _OFFSCREEN = QPointF(-999_999, -999_999)

        # Snapshot existing items by id() so we can tell a reused
        # singleton from a newly-created node regardless of where its
        # position landed after the factory's internal adjustments.
        existing_ids = {id(item) for item in self.scene.items()}

        try:
            node = add_fn(pos=_OFFSCREEN, **kwargs)
        except Exception:
            logger.exception("Failed to spawn node via %s", add_fn.__name__)
            return None
        if node is None:
            return None

        # Singleton-reuse detection — the returned node already lived in
        # the scene before we asked for a new one.
        if id(node) in existing_ids:
            self._animate_camera_to(node.sceneBoundingRect().center())
            self._status(f"already have a {type(node).__name__} — heading there")
            return node

        origin = self._viewport_spawn_anchor()
        clear_pos = spiral_place(self.scene, node, origin=origin)
        node.setPos(clear_pos)

        from utils.audio import audio
        audio.play_chime()
        self._status(status_msg)
        return node

    def _animate_camera_to(self, target: "QPointF", duration: int = 250):
        """Smoothly pan the viewport to centre on *target* in scene coords.

        Uses the same 250ms InOutSine easing as BaseNode's shelf reveal
        so the camera move reads as intentional motion rather than a
        snap — the visual grammar of 'pay attention here' is shared
        across the app."""
        from PySide6.QtCore import QVariantAnimation, QEasingCurve, QPointF
        vp = self.view.viewport()
        start = self.view.mapToScene(vp.width() // 2, vp.height() // 2)
        anim = QVariantAnimation(self)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def _tick(t):
            x = start.x() + (target.x() - start.x()) * t
            y = start.y() + (target.y() - start.y()) * t
            self.view.centerOn(QPointF(x, y))

        anim.valueChanged.connect(_tick)
        anim.start()
        # Keep a reference so the animation isn't garbage-collected
        # mid-flight.  Replaces any previous pan animation in progress.
        self._camera_anim = anim

    def _spawn_warm_node(self):        self._spawn(self.scene.add_warm_node,         "a warm thought arrives")
    def _spawn_about_node(self):       self._spawn(self.scene.add_about_node,        "a little note for later")
    def _spawn_bezier_node(self):      self._spawn(self.scene.add_bezier_node,       "curves ahead")
    def _spawn_health_node(self):      self._spawn(self.scene.add_health_node,       "checking in on things")
    def _spawn_claude_node(self):
        """
        Summon the Companion to the current scene.

        One ClaudeNode lives in the entire app — a friend held across session
        switches, not a per-session artefact. Three cases:
        - already here → pan camera to it and select it
        - exists but parked between sessions → place it at this session's seat
        - never created → create it, stash the reference on the app
        """
        from PySide6.QtCore import QPointF
        from nodes.ClaudeNode import ClaudeNode

        # Case 1: already in current scene — focus + select
        if self._companion is not None and self._companion.scene() is self.scene:
            try:
                self.scene.clearSelection()
                self._companion.setSelected(True)
                self.view.centerOn(self._companion)
            except Exception:
                pass
            self._status("claude is right here")
            return

        # Compute landing position — this session's remembered seat, or centre
        seat = self._companion_seats.get(self._current_companion_seat_key() or "")
        if seat:
            target = QPointF(seat[0], seat[1])
        else:
            target = self.view.mapToScene(self.view.viewport().rect().center())

        # Case 2: exists but parked — attach to current scene at the seat
        if self._companion is not None:
            try:
                self.scene.addItem(self._companion)
                r = self._companion.rect()
                self._companion.setPos(target - QPointF(r.width() / 2, r.height() / 2))
                self.scene.raise_node(self._companion)
                self._status("claude has entered the chat")
                return
            except Exception:
                # Companion reference went stale — fall through and recreate
                self._companion = None

        # Case 3: first spawn ever — create via the scene's factory, then claim
        node = self.scene.add_claude_node(target)
        node._is_companion = True
        # _pinned_across_scenes opts this node out of BaseNode.itemChange's
        # scene→None demolition trigger so cross-scene moves (to limbo and
        # back) don't tear it down mid-flight. Read the warning block in
        # BaseNode.itemChange before adding this flag to any other node —
        # it disables the safety net that prevents inner-widget signal
        # crashes (see Documents/Compliance/Node Cleanup Compliance.md,
        # 2026-04-18 ClaudeNode inner-widget signal-destructor race).
        node._pinned_across_scenes = True
        self._companion = node
        self._status("claude has entered the chat")
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
    def _spawn_premiere_bridge_node(self): self._spawn(self.scene.add_premiere_bridge_node, "bridge opening to Premiere")

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
            "premiere_bridge": self._spawn_premiere_bridge_node,
        }
        self._action_dispatch = {
            "restore":           self._restore_deleted,
            "snip":              self._start_wire_snip,
            "launch_claude":     self._launch_claude_app,
            "launch_claude_code": self._launch_claude_code,
        }

    def _show_sidebar_menu(self, menu, btn) -> None:
        """Execute a sidebar-category menu anchored below ``btn`` with a toggle-on-repeat guard.

        Qt's default behaviour when the launcher button of an open popup is
        clicked is to dismiss the popup AND then fire the button's clicked
        signal — which re-enters the menu-show handler and immediately
        re-opens the menu. That defeats the "click again to close" mental
        model every other toggle in the app uses; users end up having to
        click outside the menu just to reach the category button beneath
        the open one.

        The guard breaks that loop by:

          1. On ``aboutToHide``, recording ``btn`` + timestamp IFF the
             cursor is still inside ``btn`` — meaning the close was
             triggered by clicking the launcher. Clicks outside the menu,
             selected actions, and Esc dismissals leave the flag cleared,
             so those paths keep their natural behaviour.
          2. On subsequent show for the same ``btn`` within 150 ms,
             swallowing the show and clearing the flag.

        Both ``_show_category_menu`` and ``_show_info_menu`` route through
        here so every sidebar button gets the same toggle behaviour.
        """
        import time
        from PySide6.QtGui import QCursor

        if (getattr(self, '_sidebar_menu_just_closed_for', None) is btn and
                (time.time() - getattr(self, '_sidebar_menu_just_closed_time', 0.0)) < 0.15):
            self._sidebar_menu_just_closed_for = None
            return

        def _on_hide(b=btn):
            gp = QCursor.pos()
            if b.rect().contains(b.mapFromGlobal(gp)):
                self._sidebar_menu_just_closed_for = b
                self._sidebar_menu_just_closed_time = time.time()
        menu.aboutToHide.connect(_on_hide)

        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_category_menu(self, category: str, btn: QPushButton) -> None:
        """Build a category menu from node_registry.toml entries."""
        from utils.persistence import registry

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

        self._show_sidebar_menu(menu, btn)

    def _show_text_menu(self, btn):    self._show_category_menu("text", btn)
    def _show_images_menu(self, btn):  self._show_category_menu("images", btn)
    def _show_audio_menu(self, btn):   self._show_category_menu("audio", btn)
    def _show_visual_menu(self, btn):  self._show_category_menu("visual", btn)
    def _show_health_menu(self, btn):  self._show_category_menu("health", btn)
    def _show_tools_menu(self, btn):   self._show_category_menu("tools", btn)
    def _show_info_menu(self, btn):
        """Info menu: registry entries + dynamic Documents/*.md files."""
        from pathlib import Path
        from utils.persistence import registry

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
        _SKIP_DIRS = {"data", "Data"}
        if docs_dir.is_dir():
            fallback_pix = Theme.icon(Theme.iconSession, fallback_color="#8a9aaa")

            def _transform_memory_index(raw: str) -> str:
                """MEMORY.md uses a bulleted-index format (`- [Name](file) — description`)
                rather than the H2+body shape the rest of the Documents tree uses.
                The MarkdownNode splitter only knows about markdown headings, so
                we rewrite each bullet line into `## Name` + description to feed
                the splitter its native food. Non-bullet lines pass through untouched.
                Dashes are permissive — em, en, and hyphen all accepted."""
                import re
                bullet = re.compile(r'^-\s+\[([^\]]+)\]\([^)]+\)\s*[—–\-]\s*(.+)$')
                out = []
                for line in raw.splitlines():
                    m = bullet.match(line)
                    if m:
                        out.append(f"## {m.group(1).strip()}")
                        out.append(m.group(2).strip())
                        out.append("")
                    else:
                        out.append(line)
                return "\n".join(out)

            def _make_doc_action(target_menu, md_path):
                act = target_menu.addAction(QIcon(fallback_pix), md_path.stem)
                def _spawn_doc(_, p=md_path):
                    try:
                        text = p.read_text(encoding="utf-8")
                    except Exception:
                        self._status(f"could not read {p.name}")
                        return
                    # Memory index: rewrite bullets into H2+body so each entry
                    # becomes its own focal chunk on the canvas, matching how
                    # the other Docs .md files split by heading.
                    if p.name == "MEMORY.md":
                        text = _transform_memory_index(text)
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
                    # Quiet the QObject layer synchronously first: the 100ms
                    # delivery timer would otherwise race Qt's C++ destructor
                    # during the deferred removeItem and trip a c0000409
                    # fastfail in Qt6Core.dll. See 2026-04-18 entry in
                    # Documents/Compliance/Node Cleanup Compliance.md.
                    node._quiet_background_machinery()
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

            # Memory folder — Claude Code's per-session AI state, exposed as
            # a second scan root so the same MarkdownNode proofreading pipeline
            # serves out-of-repo memory files too. Silently absent when Claude
            # Code isn't installed on this machine or the encoded folder name
            # doesn't match (encoding mirrors Claude Code's own mapping:
            # drive-letter colon and path separators replaced with dashes).
            project_root = Path(__file__).resolve().parent
            cwd_encoded = (
                str(project_root).replace(":", "-").replace("\\", "-").replace("/", "-")
            )
            memory_dir = Path.home() / ".claude" / "projects" / cwd_encoded / "memory"
            if memory_dir.is_dir():
                # MEMORY.md is the index of everything else — pin it first
                # so the table of contents reads before its entries. Windows
                # Path sort is case-insensitive by default, which otherwise
                # buries it mid-list around the other m-prefixed names.
                memory_mds = sorted(
                    (p for p in memory_dir.iterdir()
                     if p.is_file() and p.suffix.lower() == ".md"),
                    key=lambda p: (p.name != "MEMORY.md", p.name.lower()),
                )
                if memory_mds:
                    menu.addSeparator()
                    mem_submenu = self._styled_menu()
                    for i, md_path in enumerate(memory_mds):
                        _make_doc_action(mem_submenu, md_path)
                        # Separator after the index, before the entries
                        if i == 0 and md_path.name == "MEMORY.md" and len(memory_mds) > 1:
                            mem_submenu.addSeparator()
                    menu.addMenu(mem_submenu).setText("Memory")

        # ── Diagnostics ─────────────────────────────────────────────────
        # Image-stamp + cache validation audit.  Walks every ImageNode in
        # the active scene, compares source vs cache hashes, checks for
        # stamp-placement anomalies (the "stamp on cache instead of
        # source" pathology the audit exists to catch), and spawns a
        # chain of findings on the canvas so every anomaly is visible
        # and actionable.  See utils/audit/image_stamps.py.
        menu.addSeparator()
        audit_pix = Theme.icon(Theme.iconSession, fallback_color="#9a8a7a")
        audit_act = menu.addAction(QIcon(audit_pix), "Audit Image Stamps…")
        audit_act.setToolTip(
            "Scan every ImageNode for source/cache drift and stamp-placement "
            "anomalies.  Surfaces the report as an AboutNode chain on the canvas."
        )
        audit_act.triggered.connect(self._run_image_stamp_audit)

        self._show_sidebar_menu(menu, btn)
    def _show_claude_menu(self, btn):  self._show_category_menu("claude", btn)

    # ─────────────────────────────────────────────────────────────────────────
    # IMAGE STAMP AUDIT — diagnostic entry point
    # ─────────────────────────────────────────────────────────────────────────

    def _run_image_stamp_audit(self) -> None:
        """Run the image-stamp validation audit and present the result
        on the canvas as an AboutNode chain.

        The chain anchors near the current viewport centre so the user
        sees the report without hunting for it.  Each finding becomes
        one AboutNode; clean-scene case produces a single affirming
        node.  The full formatted report also lands in the log for
        forensic retention.
        """
        from utils.audit.image_stamps import audit_and_log
        from utils.placement import spiral_place, wander_origin
        from graphics.Connection import Connection

        report = audit_and_log(self.scene)

        # Build the list of report lines that become AboutNode labels.
        # Clean-scene case: a single affirming line so the user gets
        # visible confirmation that the run happened.
        if report.is_clean() and report.total_image_nodes > 0:
            lines = [report.summary_line()]
        elif report.total_image_nodes == 0:
            lines = ["No ImageNodes in scene — nothing to audit"]
        else:
            # Headline + per-bucket findings, one AboutNode per line.
            lines = [report.summary_line()]
            for bucket in (report._CRITICAL_BUCKETS
                           + report._WARN_BUCKETS
                           + report._INFO_BUCKETS):
                items = getattr(report, bucket)
                if not items:
                    continue
                severity = ("CRITICAL" if bucket in report._CRITICAL_BUCKETS
                            else "WARN"  if bucket in report._WARN_BUCKETS
                            else "INFO")
                lines.append(f"— {severity}: {bucket} ({len(items)}) —")
                for f in items:
                    short_uuid = f.uuid[:8] if f.uuid else "?"
                    src_tail = (f.source_path.split('\\')[-1].split('/')[-1]
                                if f.source_path else "<no source>")
                    lines.append(f"{short_uuid}  {src_tail}: {f.detail}")

        if not lines:
            return

        from PySide6.QtCore import QPointF
        _OFFSCREEN = QPointF(-999_999, -999_999)

        # Anchor first node near the current viewport centre.  Every
        # subsequent spawn wanders off the previous one, same pattern
        # TextNode's split uses — keeps the chain tidy and organic.
        prev_node = None
        for line in lines:
            node = self.scene.add_about_node(pos=_OFFSCREEN, label=line)
            node.data.title = line[:40]

            if prev_node is None:
                # Viewport-centred first anchor via spiral_place's None origin.
                pos = spiral_place(self.scene, node)
            else:
                chain_origin = wander_origin(prev_node)
                pos = spiral_place(
                    self.scene, node, origin=chain_origin,
                    parent=prev_node, fallback=chain_origin,
                )
            node.setPos(pos)

            if prev_node is not None:
                conn = Connection(prev_node, node)
                self.scene.addItem(conn)
            prev_node = node

        # Whisper a summary via the InfoBar so the user knows the run
        # fired even if the chain lands outside their current viewport.
        self.show_info(report.summary_line())

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
        # session lives in {project}/Documents/Data/ — project root is three levels up
        project_root = path.parent.parent.parent if path else None
        self._spawn(self.scene.add_tree_node, "mapping the territory",
                    project_path=str(project_root) if project_root else "")

    def _spawn_info_node(self):
        self._spawn(self.scene.add_info_node, "version 0.6.0")

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
        # Zero vertical outer margins so the dormant bottomToolbar matches
        # the top toolbar's Theme.handleHeightTop exactly. When the bench
        # wakes up, the buttons_row's own height stacks below with the 4px
        # inter-item spacing supplying the visual breathing room.
        outer.setContentsMargins(10, 0, 10, 0)
        outer.setSpacing(4)

        # ── Info bar row ──────────────────────────────────────────────────────
        # Height matches Theme.handleHeightTop so the bottom infobar sits at
        # exactly the same thickness as the top titlebar when dormant.
        _info_bar_row = QWidget()
        _info_bar_row.setFixedHeight(Theme.handleHeightTop)
        _info_bar_row.setStyleSheet("background: transparent;")
        _info_bar_layout = QHBoxLayout(_info_bar_row)
        _info_bar_layout.setContentsMargins(0, 0, 0, 0)
        _info_bar_layout.setSpacing(0)

        self.info_label = pretty_label("", alignment=Qt.AlignCenter)
        # Bottom padding nudges the text upward so it reads centered in y —
        # italic Chandler42 at 16px has a visual centre below its geometric
        # one (ascenders are larger than descenders), so without the nudge
        # the glyphs feel pinned to the window's bottom edge.
        self.info_label.setStyleSheet(
            f"background: transparent; border: none; padding: 0px 4px 4px 4px;"
            f" color: {Theme.textPrimary}; font-family: Chandler42; font-weight: 500; font-style: italic; font-size: 16px;"
        )
        self.info_label.setFixedHeight(Theme.handleHeightTop)

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

        # ── Right group — eXid test bench for new utility buttons ───────────
        # The staging area for utilities whose value is still being evaluated.
        # Promotion pipeline:
        #   1. Park new utility here via self._make_exid_button(...)
        #   2. Use it for ~1–2 weeks in real sessions
        #   3. If used regularly → graduate to a permanent home
        #      (titlebar right-click menu, sidebar, etc.)
        #   4. If unused → just remove it
        # Currently empty — the most recent graduates (Sound, Polaroid)
        # moved to the titlebar context menu as permanent entries. This is
        # the first time the bench has been clear; expect new candidates
        # to land here soon.
        right_group = QWidget()
        right_group.setStyleSheet("background: transparent;")
        right_layout = QHBoxLayout(right_group)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

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

        # Save references so _make_exid_button can place new candidates
        # into right_layout and auto-show the bench when it wakes up.
        self._exid_right_layout = right_layout
        self.buttons_row = _ButtonBar(left_group, right_group, self._bottom_progress)
        outer.addWidget(self.buttons_row)

        # Dormant-state shrink: when both bench groups are empty, hide the
        # buttons_row so the bottom toolbar collapses to just the infobar.
        # Hidden bench → thin toolbar → when a new test button lands, the
        # bench wakes up and the toolbar visibly thickens. Thickness is
        # the incentive to keep an eye on what's parked there.
        if left_layout.count() == 0 and right_layout.count() == 0:
            self.buttons_row.hide()

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
        """Slider dragged — set the view zoom to the slider's value.

        Guarded against self.view not existing: the sidebar (and hence
        this slider) is now built earlier in __init__ than the view,
        and setting the slider's initial value fires valueChanged once
        during construction. Silently no-op until the view lands.
        """
        if not hasattr(self, 'view'):
            return
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
        The state-driven label lives in the titlebar context menu, which
        regenerates on each right-click and reads the current mute state.
        """
        from utils.audio import audio
        muted = not audio.is_muted()
        audio.set_muted(muted)
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

    # =========================================================================
    # Meov — the cat minding the app while the curtains are up
    # =========================================================================

    _MEOV_MIN_MS = 10 * 60 * 1000   # 10 minutes
    _MEOV_MAX_MS = 15 * 60 * 1000   # 15 minutes
    _MEOV_BANG_CHANCE = 0.2         # 1 in 5 ticks swaps dots for exclamations

    def _meov_tick(self) -> None:
        """One whispered meov. Escalates by a dot each time the cat waits.
        Occasionally swaps the dots for a single or double exclamation when
        the cat wants to sound a little more insistent than usual."""
        self._meov_level += 1
        if random.random() < self._MEOV_BANG_CHANCE:
            message = "meov" + ("!" * random.randint(1, 2))
        else:
            message = "meov" + ("." * self._meov_level)
        self.show_info(message)
        self._meov_timer.start(random.randint(self._MEOV_MIN_MS, self._MEOV_MAX_MS))

    def _start_meov(self) -> None:
        """Begin the countdown. Called when the curtains roll up."""
        self._meov_level = 0
        self._meov_timer.start(random.randint(self._MEOV_MIN_MS, self._MEOV_MAX_MS))

    def _stop_meov(self) -> None:
        """Halt the cat. Called when the curtains come back down."""
        if hasattr(self, '_meov_timer'):
            self._meov_timer.stop()
        self._meov_level = 0

    def _active_info_surface(self):
        """Pick which InfoBar surface should host the next message.

        The InfoBar is one channel with two possible stages. When the bottom
        bar's strip is not visible — curtains rolled up, or splitter dragged
        so far down that the strip is gone — the message routes to the
        titlebar mirror instead, preserving the same typewriter + fade
        personality on the smaller stage.
        """
        curtains_up = getattr(self, 'is_collapsed', False)
        try:
            bottom_h = self._v_splitter.sizes()[1] if hasattr(self, '_v_splitter') else 999
        except Exception:
            bottom_h = 999
        # Strip is considered visible if bottom has room for at least the info row
        strip_visible = (not curtains_up) and bottom_h >= 20
        if strip_visible:
            return self.info_label, self._info_opacity
        return self.info_label_top, self._info_opacity_top

    def show_info(self, message: str, on_click=None) -> None:
        """Typewriter reveal with simultaneous fade-in, hold 3 s, then fade out."""
        self._info_timer.stop()
        if hasattr(self, '_tw_timer') and self._tw_timer is not None:
            self._tw_timer.stop()

        # Pick the stage at show-time. A message already in flight uses the
        # stage it started on; picking a new one every tick would get jumpy
        # if the user changes modes mid-whisper.
        self._active_label, self._active_opacity = self._active_info_surface()

        self._tw_full    = message
        self._tw_index   = 0
        self._info_click_action = on_click
        self._active_label.setText("")
        self._active_label.setCursor(
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
        target = getattr(self, '_active_label', self.info_label)
        target.setText(self._tw_full[:self._tw_index])
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
        target = getattr(self, '_active_label', self.info_label)
        target.setCursor(Qt.ArrowCursor)
        self._animate_info_opacity(1.0, 0.0, 600)

    def _animate_info_opacity(self, start: float, end: float, duration: int) -> None:
        if self._info_anim:
            self._info_anim.stop()
        effect = getattr(self, '_active_opacity', self._info_opacity)
        self._info_anim = QPropertyAnimation(effect, b"opacity")
        self._info_anim.setDuration(duration)
        self._info_anim.setStartValue(start)
        self._info_anim.setEndValue(end)
        self._info_anim.start()

    def _sync_zoom_slider(self) -> None:
        """Called after wheel-zoom to keep the slider in sync with the view."""
        value = int(round(self.view.current_zoom * 100))
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(max(3, min(500, value)))
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

    # ── The Companion — app-scoped ClaudeNode lifecycle ──────────────────────
    #
    # One ClaudeNode lives at the app level and travels with the user across
    # session switches. Its scene membership changes; its identity, state and
    # (eventually) conversation do not. Seat positions are remembered per
    # session so it arrives where it was last seen in each place.
    #
    # Wires touching the companion do not persist between sessions — each API
    # call is its own context, and any connection on the companion at save
    # time is by definition transient. They drop when the companion parks.

    def _companion_sidecar_path(self):
        """Fixed app-global path for the companion seat map."""
        from pathlib import Path as _P
        return _P(__file__).resolve().parent / "Documents" / "Data" / "companion.json"

    def _load_companion_seats(self) -> dict:
        """Load the session_key → (x, y) seat map from sidecar, or {} if absent."""
        import json
        p = self._companion_sidecar_path()
        if not p.exists():
            return {}
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            # Normalise to dict[str, list[float]]
            return {str(k): list(v) for k, v in raw.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2}
        except Exception:
            logger.exception("[companion] failed to load seats sidecar")
            return {}

    def _save_companion_seats(self) -> None:
        """Persist the seat map. Non-fatal on failure."""
        import json
        try:
            p = self._companion_sidecar_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._companion_seats, indent=2),
                         encoding="utf-8")
        except Exception:
            logger.exception("[companion] failed to save seats sidecar")

    def _current_companion_seat_key(self) -> str | None:
        """Key under which to record the companion's seat for the active session."""
        try:
            path = self._session_path()
        except Exception:
            return None
        return str(path) if path else None

    def _park_companion(self) -> None:
        """
        Called before a scene swap. Records the companion's current seat,
        severs any wires touching it, and transfers it into the limbo scene.
        The companion object itself lives on — 'in the between'.

        Transfer via limbo.addItem (not removeItem) is deliberate: moving a
        node directly between scenes fires ItemSceneChange with the new scene
        value, skipping the None transition that would otherwise trigger
        BaseNode's demolition path.
        """
        if self._companion is None:
            return
        if self._companion.scene() is not self.scene:
            return  # Already parked (in limbo) or scene-less

        # Record seat under outgoing session's key
        key = self._current_companion_seat_key()
        if key:
            try:
                p = self._companion.scenePos()
                self._companion_seats[key] = [p.x(), p.y()]
            except Exception:
                pass

        # Drop any Connection items touching the companion — wires on the
        # companion are always transient per-context, never session property.
        try:
            from graphics.Connection import Connection
            for item in list(self.scene.items()):
                if isinstance(item, Connection) and (
                    item.start_node is self._companion
                    or item.end_node is self._companion
                ):
                    try:
                        self.scene.removeItem(item)
                    except Exception:
                        pass
        except Exception:
            logger.exception("[companion] wire sever failed during park")

        # Transfer to limbo. Qt's cross-scene addItem is NOT atomic: it fires
        # ItemSceneChange with value=None mid-flight, which would normally
        # trip BaseNode's demolition path. The companion's
        # _pinned_across_scenes flag opts out of that trigger so the transfer
        # survives intact. See BaseNode.itemChange for the full warning.
        try:
            self._companion_limbo.addItem(self._companion)
        except Exception:
            logger.exception("[companion] transfer to limbo failed")

    def _attach_companion(self) -> None:
        """
        Called after a session load completes. Places the companion in the
        incoming scene at the seat remembered for this session, or at the
        current viewport centre if this is the first visit.
        """
        if self._companion is None:
            return
        if self._companion.scene() is self.scene:
            return  # Already here
        from PySide6.QtCore import QPointF
        key = self._current_companion_seat_key()
        seat = self._companion_seats.get(key or "") if key else None
        if seat:
            target = QPointF(seat[0], seat[1])
        else:
            target = self.view.mapToScene(self.view.viewport().rect().center())
        try:
            self.scene.addItem(self._companion)
            r = self._companion.rect()
            self._companion.setPos(target - QPointF(r.width() / 2, r.height() / 2))
            self.scene.raise_node(self._companion)
        except Exception:
            logger.exception("[companion] attach failed — companion reference cleared")
            self._companion = None

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
        project_dir = path.parent.parent.parent  # Documents/Data/session → project root
        if project_dir.exists() and not (project_dir / ".git").exists():
            self._git_init_project(project_dir, project_dir.name)
        try:
            from utils.persistence.media_cache import set_cache_root
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
        # Residue indicator — stray *.intricate siblings (debug copies,
        # ctrl-c/ctrl-v leftovers) get a sticky note at view focus so the
        # user can inspect and manually sweep. Never auto-deleted.
        residue = session_residue(path)
        if residue:
            QTimer.singleShot(50, lambda r=residue: self._spawn_residue_notice(r))
        # Unblock autosave after the initial scene.changed burst settles
        def _unblock():
            self._autosave_blocked = False
        QTimer.singleShot(3000, _unblock)

    def _spawn_residue_notice(self, residue: list) -> None:
        """Spawn an AboutNode at view centre listing residue *.intricate files."""
        try:
            names = "\n".join(f"• {p.name}" for p in residue)
            label = (
                "session residue detected\n"
                "(stray .intricate files alongside the live session — "
                "left in place for manual review)\n\n"
                f"{names}"
            )
            center_scene = self.view.mapToScene(self.view.viewport().rect().center())
            self.scene.add_about_node(pos=center_scene, label=label)
        except Exception as e:
            from pretty_widgets.utils.logger import setup_logger
            setup_logger("session").warning(f"residue notice spawn failed: {e}")

    def _autosave(self) -> None:
        """Save the current canvas to the active project's session.json."""
        if getattr(self, '_autosave_blocked', False):
            return
        if self.project_selector.currentText() == self._NEW_SESSION_SENTINEL:
            return
        # Never overwrite a session with an empty scene — protects against
        # save-on-close after a failed load wiping valid session data.
        # Duck-typed over any node root (BaseNode, StickerNode, future).
        has_nodes = any(hasattr(i, 'to_dict') and hasattr(i, 'data')
                        for i in self.scene.items())
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

        # Park the companion before save — records its seat, severs wires,
        # and removes it from the outgoing scene so it isn't caught up in
        # the save loop or the impending scene teardown.
        self._park_companion()

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
        self._attach_companion()
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
            ensure_dir(project_dir / "Documents" / "Data")
            self._git_init_project(project_dir, name)

        # Park the companion before save — see on_session_changed for rationale
        self._park_companion()

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
        self._attach_companion()
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
            # ── Meov timer ──────────────────────────────────────────────────
            # While the curtains are rolled up the app whispers "meov" at
            # escalating seriousness (one more dot each tick). Intermittent
            # exclamation variants keep the cat's voice feeling alive.
            # Resets and stops when the curtains come back down. The timer
            # is armed here but doesn't start until toggle_curtains lifts it.
            self._meov_level = 0
            self._meov_timer = QTimer(self)
            self._meov_timer.setSingleShot(True)
            self._meov_timer.timeout.connect(self._meov_tick)

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
        # Release the singleton port so the restart child can acquire it
        # before we start fading out. Without this the child's
        # is_singleton probe finds us still holding the port, exits
        # silently, and the visible effect is "the X-button-restart
        # feature stopped working" — even though the fade + spawn path
        # is otherwise intact.
        try:
            from shared_braincell import release_singleton
            release_singleton(appName)
        except Exception:
            pass
        # Legacy fallback — older is_singleton implementations stored the
        # socket on sys.modules['__main__']._instance_lock; harmless if
        # the attribute isn't present.
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
            # Defensive: stop + disconnect long-running UI timers before the
            # C++ window tears down. These are parented to self (so Qt would
            # collect them eventually), but any tick that fires between
            # event.accept() and final destruction could touch half-torn state.
            # Part of the Node Cleanup Compliance 2026-04-17 Tier 2 sweep.
            for _name, _slot in (
                ('_joy_timer',   getattr(self, '_deplete_joy',       None)),
                ('_happy_timer', getattr(self, '_tick_happy',        None)),
            ):
                _t = getattr(self, _name, None)
                if _t is None:
                    continue
                try:
                    _t.stop()
                except RuntimeError:
                    pass
                if _slot is not None:
                    try:
                        _t.timeout.disconnect(_slot)
                    except RuntimeError:
                        pass
            try:
                import threading
                threading.Thread(target=self._cleanup_pycache, daemon=True).start()
                self._persist_claude_node_size()
            except (RuntimeError, Exception):
                pass
            # Record the companion's final seat, then persist the seat map so
            # the next launch remembers where to place it. We don't move it to
            # limbo on close — natural Qt teardown handles cleanup and we just
            # need the coordinates recorded before the scene goes away.
            try:
                if (self._companion is not None
                        and self._companion.scene() is self.scene):
                    key = self._current_companion_seat_key()
                    if key:
                        p = self._companion.scenePos()
                        self._companion_seats[key] = [p.x(), p.y()]
                self._save_companion_seats()
            except Exception:
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
