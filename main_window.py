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
from nodes._dialog_helper import _DialogChoreographyMixin
from pretty_widgets.PrettyDialog import PrettyDialog
from pretty_widgets.PrettyButton import button
from pretty_widgets.PrettyMenu import menu as pretty_menu
from shared_braincell.logger import setup_logger
from shared_braincell.phrase_picker import randomling as pick_phrase
from shared_braincell.settings import appName, set_nested, get_nested, set_value, get
from utils.helpers import ensure_dir, clean_pycache
from utils.persistence.session import session_path, enter_project, session_residue
from pretty_widgets.PrettyCombo import combo as pretty_combo
from pretty_widgets.PrettyLabel import label as pretty_label
from pretty_widgets.PrettySlider import slider as pretty_slider

# Optional side log writer — graceful absence.  The clean_pycache()
# janitor wipes every *.pyc on exit, so a .pyc-only delivery for this
# module is incompatible with the existing housekeeping.  When the
# import fails (file doesn't exist on disk), the rest of the app keeps
# working; the structured [joy-wake] log line still emits, only the
# narrative side log goes silent until a janitor-compatible binary
# format is wired in.
try:
    from joy import joy_narrative as _joy_narrative
except ImportError:
    _joy_narrative = None

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


class _NewSessionDialog(PrettyDialog):
    """Frameless new-session dialog — the ceremony of naming a piece.

    Inherits PrettyDialog from the Pretty Widgets package: explicit screen
    centring, HWND_TOPMOST defence on Windows, activate/raise on show, plus
    the family's shared visual chrome (frameless + translucent + themed
    container) auto-applied via PrettyDialog.__init__. Subclass body is
    a handful of lines naming the prompt, building the input, and wiring
    the button row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.content_layout.addWidget(
            self.make_prompt_label("Name your next masterpiece:")
        )
        # Placeholder picked fresh from the shared phrase bank each time the
        # dialog opens — every new project is announced with its own little
        # uplifting sample.
        self._input = self.make_input(placeholder=f"{pick_phrase()}…")
        self._input.committed.connect(lambda _t: self.accept())
        self.content_layout.addWidget(self._input)
        self.content_layout.addLayout(
            self.make_button_row(accept_label="Create")
        )
        self._input.setFocus()

    def name(self) -> str:
        return self._input.toPlainText().strip()


class IntricateApp(QMainWindow, _DialogChoreographyMixin):
    def __init__(self):
        super().__init__()
        # ── Chrome-pulse registry ─────────────────────────────────────────
        # Surfaces that share Theme.windowBg as their background register
        # here at construction.  When the joy bar drops below the hungry
        # threshold the registered surfaces pulse dark → bright pink →
        # dark together as a continuous "she's hungry" signal until fed.
        # Each entry is a (widget, qss_template_with_{bg}) tuple — the
        # animation re-formats the template on every tick.
        self._chrome_pulse_targets: list[tuple[QWidget, str]] = []

        # 1. The civil pleasantries
        self.setWindowTitle("Our Love As Intricate As The Patterns We Impose")
        _qmw_template = "QMainWindow {{ background-color: {bg}; }}"
        self.setStyleSheet(_qmw_template.format(bg=Theme.windowBg))
        self._chrome_pulse_targets.append((self, _qmw_template))
        self.setWindowOpacity(0.0)

        # 2. The Beautiful and Prestigious Top Toolbar things with all it's specifics
        self._dragging_window = False
        self._resizing_window = False
        self._drag_pos = None
        self.is_collapsed = False
        self._is_fullscreen = False
        self._shown_once = False

        # Curtain animation perf instrumentation — Phase 1 of the
        # "lag on resume after long idle" hunt.  Per-frame timings are
        # accumulated into self._curtain_perf during each rolldown /
        # rollup, then digested into one summary log line on settle.
        # _last_finished_t is the wallclock-monotonic timestamp of the
        # previous curtain animation's settle moment — the gap between
        # that and the next .start() is our "idle duration" proxy
        # (long gap = the user came back from a sleep / step-away).
        self._curtain_perf_last_finished_t: float = 0.0
        self._curtain_perf: dict | None = None

        # Curtain keep-warm timer — Phase 1 remediation hypothesis from
        # Documents/Compliance/Curtain Resume Lag Investigation.md.  The
        # diagnosis identified Bucket 2 (sustained cold paint pipeline)
        # as the dominant cause of slow first rolldowns after long
        # absences.  Hover pulses naturally keep the pipeline warm
        # during active use — but they only fire on cursor proximity
        # to nodes, so an absent user produces zero ambient paint
        # activity once curtains roll up.  This timer fires a tiny
        # update() every 5 min while curtains are up, scheduling one
        # paintEvent which DWM composites — enough to keep the
        # compositor caches referenced and (we hypothesise) prevent
        # the Bucket 2 recovery cost on the next rolldown.  The next
        # curtain-perf log line is annotated with keep_warm=N to tell
        # us how many pulses fired during the gap, so the data answers
        # whether the mitigation worked.
        self._keep_warm_pulse_count: int = 0
        self._KEEP_WARM_INTERVAL_MS = 5 * 60 * 1000   # 5 minutes
        self._keep_warm_timer = QTimer(self)
        self._keep_warm_timer.setInterval(self._KEEP_WARM_INTERVAL_MS)
        self._keep_warm_timer.timeout.connect(self._on_keep_warm_tick)

        # Phase 2 perf heartbeat — Phase 1 keep_warm data showed the
        # mitigation helped at sub-hour idle but failed for multi-hour
        # idle, with a partial first-frame improvement.  Shape suggests
        # working-set page trim is the dominant remaining cause; this
        # heartbeat captures the data needed to confirm.
        #
        # Every 60 s, write one CSV row with: timestamp, RSS, GC counts,
        # scene item count, curtain state, and gap-since-previous-tick.
        # The gap-since-previous-tick is the natural wake signal — when
        # Windows enters sleep / lock states, QTimer pauses; when it
        # wakes, the next tick lands with a gap much larger than the
        # 60 s interval.  Post-hoc analysis can flag wake events from
        # the gap column without OS-level session hooks.
        #
        # CSV is append-only at Documents/Data/curtain_perf.csv so data
        # accumulates across restarts (today's restart pattern needs
        # this).  Curtain-perf log lines also report
        # `since_heartbeat_gap=Ns` — distinguishing "first click after
        # wake" from "click after warming up with other activity".
        from pathlib import Path as _Path
        self._PERF_HEARTBEAT_INTERVAL_MS = 60 * 1000   # 60 seconds
        self._perf_csv_path: _Path = (
            _Path(__file__).resolve().parent / "Documents" / "Data" / "curtain_perf.csv"
        )
        self._joy_narrative_path: _Path = (
            _Path(__file__).resolve().parent / "Documents" / "Data" / "joy_wake_narrative.log"
        )
        # Scene-items categorized breakdown — written each heartbeat
        # alongside the curtain_perf.csv row.  Each line is one JSON
        # object: {"ts":"...","TypeName":count,...}.  Captures which
        # CLASS of QGraphicsItem is fluctuating when the aggregate
        # scene_items count moves — undifferentiated len(scene.items())
        # can't tell if the wobble is nodes, connections, particles, or
        # something else accumulating.  Separate file so the existing
        # CSV format stays unchanged.
        self._scene_breakdown_path: _Path = (
            _Path(__file__).resolve().parent / "Documents" / "Data" / "scene_breakdown.log"
        )

        # Windows session lock/unlock observation — captures the
        # screen-lock-state variable directly so curtain-perf rows
        # can tag against it without controlled experiments.  Hooks
        # into Windows via WTSRegisterSessionNotification + the
        # nativeEvent handler below.  See [session] log lines for
        # LOCK / UNLOCK transitions; curtain-perf log lines gain a
        # since_unlock field reporting time since the most recent
        # observed unlock.
        self._is_locked: bool = False
        self._last_lock_t: float = 0.0
        self._last_unlock_t: float = 0.0
        self._WTS_SESSION_LOCK   = 0x7
        self._WTS_SESSION_UNLOCK = 0x8
        self._WM_WTSSESSION_CHANGE = 0x02B1
        # Defer registration until the HWND exists — show() at end of
        # __init__ wires it; QTimer.singleShot(0, ...) lands after.
        QTimer.singleShot(0, self._register_session_notification)
        self._perf_last_heartbeat_t: float = 0.0
        self._perf_last_large_gap_t: float = 0.0   # most recent post-wake landing
        self._perf_heartbeat_timer = QTimer(self)
        self._perf_heartbeat_timer.setInterval(self._PERF_HEARTBEAT_INTERVAL_MS)
        self._perf_heartbeat_timer.timeout.connect(self._on_perf_heartbeat)
        # Defer first tick until after _setup_grid wires self.scene/self.view
        # — the heartbeat reads scene state.  Started at the bottom of __init__.

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

        # JoyStats HUD — singleton at app level, like the companion. Pin state
        # gates cross-session persistence: pinned travels via limbo, unpinned
        # dies with the outgoing scene. Same two-layer protection (limbo scene
        # + _pinned_across_scenes flag) — see the companion block above for
        # the full rationale.
        self._joy_stats = None
        self._joy_stats_limbo = QGraphicsScene(self)
        self._joy_stats_seats: dict = self._load_joy_stats_seats()

        # 8. Load session for the initially selected project, then start autosave
        QTimer.singleShot(0, self._load_initial_session)

        # 9. Phase 2 perf heartbeat — starts after session load so the first
        # tick captures a representative scene-item count.  Initial timestamp
        # is set on the first tick, not at construction, so heartbeat-gap
        # measurement is meaningful from the first interval onward.
        import time as _time
        self._perf_last_heartbeat_t = _time.perf_counter()
        self._rotate_perf_logs_if_oversized()
        self._perf_heartbeat_timer.start()

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
        _top_template = "background-color: {bg};"
        self.top_toolbar.setStyleSheet(_top_template.format(bg=Theme.windowBg))
        self._chrome_pulse_targets.append((self.top_toolbar, _top_template))

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
        # Font via setFont (chandler42 helper), NOT QSS font-family — QSS
        # doesn't honour styleName, so font-family: Chandler42 alone falls
        # through to whatever Qt picks for "italic medium" and lands on
        # upright Medium more often than not.  setStyleName('Italic') via
        # the helper picks the 1843.otf script-italic Medium directly.
        from pretty_widgets.utils.fonts import chandler42
        self.info_label_top.setFont(chandler42(size_px=_info_font_px))
        # QSS routed through a small helper so the meov colour-pulse
        # animation can swap just the colour without rebuilding the
        # whole sheet on every tick.  See _titlebar_info_qss /
        # _start_meov_color_pulse below.
        self.info_label_top.setStyleSheet(self._titlebar_info_qss(Theme.textPrimary))
        self.info_label_top.setParent(self.top_toolbar)
        self._info_opacity_top = QGraphicsOpacityEffect()
        self._info_opacity_top.setOpacity(0.0)
        self.info_label_top.setGraphicsEffect(self._info_opacity_top)
        # Click → invoke the active on_click action (if any).  Mirrors the
        # bottom-bar info_label wire in _setupBottomToolbar — same channel,
        # both stages need to honour the click.  Without this, palette
        # exports / save confirmations whispered while curtains are rolled
        # leave the user with a pointer-hand cursor that does nothing.
        self.info_label_top.mousePressEvent = (
            lambda e: self._info_click_action() if getattr(self, '_info_click_action', None) else None
        )

        # Mouse-passthrough management — the label sits in the user's
        # default titlebar-drag zone, so when no message is visible we
        # want events to fall through to the QMainWindow drag handler at
        # mousePressEvent (the `pos.y() < Theme.handleHeightTop` branch).
        # When a message IS visible we want the label to receive clicks
        # so on_click handlers fire.  Initial state: no message → events
        # pass through.  show_info() flips this off when the active label
        # is info_label_top; the fade-out animation's finished signal
        # flips it back on.  See _set_info_label_top_passthrough.
        self.info_label_top.setAttribute(Qt.WA_TransparentForMouseEvents, True)

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
        # Official brand mark lives in icons/ — .ico carries the multi-res
        # layers Windows picks from, so pass the path straight to QIcon
        # rather than a single-resolution QPixmap.  Theme.iconCurtains is
        # kept as defensive last-resort: visually identical to the brand
        # mark (the share-arrow IS the family fallback per
        # project_curtains_icon_is_family_fallback memory), so even a
        # missing-file scenario still lands on the right glyph.
        _icon_path = _Path(__file__).resolve().parent / "icons" / "Stickers" / "Intricate.ico"
        if _icon_path.exists():
            self._tray_icon.setIcon(QIcon(str(_icon_path)))
        else:
            icon = Theme.icon(Theme.iconCurtains)
            self._tray_icon.setIcon(QIcon(icon) if icon and not icon.isNull() else self.windowIcon())

        # Tooltip is what Windows reads as the display name in Personalization >
        # Taskbar > "Other system tray icons".  When this is empty, Windows
        # falls back to the executable's PE FileDescription resource — which
        # for pythonw.exe-launched apps yields "Python", with whatever stale
        # IconSnapshot Windows captured the first time the entry registered.
        # Setting an explicit tooltip is the only lever that surfaces our own
        # identity in that panel.  See Documents/Design/Icon Pipeline.md ›
        # The Brand Mark Refresh Chain › step 5 for the full mechanism.
        self._tray_icon.setToolTip("Intricate")

        from pretty_widgets.PrettyMenu import PrettyMenu
        tray_menu = PrettyMenu(self)
        tray_menu.addAction("Show", self._restore_from_tray)
        tray_menu.addSeparator()
        tray_menu.addAction("Exit", self.close)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

        # Self-heal the Personalization > Taskbar panel metadata so the
        # entry there reads "Intricate" with the current brand mark
        # instead of "Python" with whatever stale icon Windows captured
        # the first time the entry was created.  This patches HKCU directly
        # for both the AUMID metadata key and any matching NotifyIconSettings
        # entries.  Silent no-op if write fails or entries don't exist yet —
        # entries materialize when the user first toggles the panel switch,
        # and the next Intricate launch picks them up.
        try:
            self._heal_systray_panel_metadata()
        except Exception:
            import logging
            logging.getLogger("intricate").debug(
                "[systray] panel-metadata self-heal raised — continuing", exc_info=True)

    def _heal_systray_panel_metadata(self) -> None:
        """Idempotent write of Personalization-panel metadata for our identity.

        Two registry surfaces:
          1. HKCU\\Software\\Classes\\AppUserModelId\\SingleSharedBraincell.Intricate
             - DisplayName = "Intricate"
             - IconUri = absolute path to icons/Stickers/Intricate.ico
             (canonical AUMID metadata; some Win11 surfaces read this)
          2. HKCU\\Control Panel\\NotifyIconSettings\\<hash>\\
             - InitialTooltip = "Intricate"  (what the panel renders as label)
             - IconSnapshot = 32x32 PNG bytes of our brand mark
             Sweep finds entries whose ExecutablePath matches our launcher
             binary's filename (python.exe / pythonw.exe / Intricate.exe).

        See Documents/Design/Icon Pipeline.md › The Brand Mark Refresh Chain
        for the full touch-point map and why Qt's setToolTip alone isn't enough.
        """
        import sys
        import winreg
        from pathlib import Path as _P
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QIcon

        _icon_path = _P(__file__).resolve().parent / "icons" / "Stickers" / "Intricate.ico"
        if not _icon_path.exists():
            return

        # ── AUMID metadata (winreg-only, no Qt needed) ─────────────────
        try:
            _aumid_key = r"Software\Classes\AppUserModelId\SingleSharedBraincell.Intricate"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _aumid_key) as k:
                winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Intricate")
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, str(_icon_path))
        except OSError:
            pass  # silent — write fails are non-fatal

        # ── NotifyIconSettings sweep (needs PNG bytes from Qt) ─────────
        _icon = QIcon(str(_icon_path))
        _pixmap = _icon.pixmap(32, 32)
        if _pixmap.isNull():
            return
        _buf = QBuffer()
        _buf.open(QIODevice.OpenModeFlag.WriteOnly)
        _pixmap.save(_buf, "PNG")
        _png_bytes = bytes(_buf.data())
        _buf.close()
        if not _png_bytes:
            return

        # Match by basename so dev (python.exe / pythonw.exe) AND frozen
        # builds (Intricate.exe) both land.  Windows aggregates python.exe
        # and pythonw.exe under one NotifyIconSettings row, so when running
        # via one we still need to patch the entry under the other.
        _my_exe = _P(sys.executable).name.lower()
        _targets = {_my_exe}
        if _my_exe == "pythonw.exe":
            _targets.add("python.exe")
        elif _my_exe == "python.exe":
            _targets.add("pythonw.exe")

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Control Panel\NotifyIconSettings") as nis:
                _i = 0
                while True:
                    try:
                        _subname = winreg.EnumKey(nis, _i)
                    except OSError:
                        break
                    _i += 1
                    try:
                        with winreg.OpenKey(nis, _subname, 0,
                                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                            try:
                                _exe, _ = winreg.QueryValueEx(k, "ExecutablePath")
                            except FileNotFoundError:
                                continue
                            if not _exe or _P(_exe).name.lower() not in _targets:
                                continue
                            winreg.SetValueEx(k, "InitialTooltip", 0,
                                              winreg.REG_SZ, "Intricate")
                            winreg.SetValueEx(k, "IconSnapshot", 0,
                                              winreg.REG_BINARY, _png_bytes)
                    except OSError:
                        continue
        except OSError:
            pass

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
                # Maximize-on-double-click is constrained to the LEFT zone of
                # the toolbar — specifically at-or-left-of the project
                # selector's right edge.  The right zone is the user's
                # default focal-zone where multiple features compound:
                # window drag, click-to-acknowledge a meov whisper, and
                # the right-click hidden context menu.  Keeping the
                # maximize override out of that zone reduces a 4-feature
                # overlap to 3, which is plenty.  The maximize button on
                # the right side of the toolbar remains the primary path;
                # this double-click is a rare override for screen-swap
                # scenarios (VR → TV resolution change where the button
                # ends up offscreen).
                try:
                    x = event.position().x()
                except AttributeError:
                    x = event.x()  # legacy Qt API fallback
                selector_right = 0.0
                if hasattr(self, 'project_selector') and self.project_selector is not None:
                    try:
                        selector_right = float(
                            self.project_selector.x() + self.project_selector.width()
                        )
                    except RuntimeError:
                        selector_right = 0.0
                if x <= selector_right:
                    logger.debug(
                        "[toolbar-dblclick] maximize fired at x=%.0f (zone right edge=%.0f)",
                        x, selector_right,
                    )
                    self.toggle_fullscreen()
                    return True
                else:
                    logger.debug(
                        "[toolbar-dblclick] ignored at x=%.0f — outside maximize zone "
                        "(zone right edge=%.0f)", x, selector_right,
                    )
                    # Fall through; let the event propagate normally so
                    # other handlers in the right zone don't get blocked.
        # ── Joy wake-on-touch ────────────────────────────────────────────────
        # Re-enabled 2026-05-05 after the third (instrumented) attempt.
        # See Documents/Compliance/Joy Sleep State Investigation.md for the
        # design intent + the historical iteration trail (a43a17c → dc207fa
        # → b82ab8b rollback in April 2026).
        #
        # Wake-on-touch is the primary reason the sleep state exists.  Direct
        # interaction with the app wakes her; OS lock/unlock and OS sleep do
        # not.  Manual button is the only way IN to sleep mode; touch is the
        # default way OUT.
        #
        # Exempt set: clicks on the sleep button (button handler is the
        # sole authority for that click, otherwise eventFilter wakes her
        # the very moment she's pressed-to-sleep) and on the curtains/tray
        # buttons (so the operator can tuck her in and immediately roll
        # curtains up / minimize without waking her on the way out).  Walk
        # up the widget tree so clicks on icon/label children of those
        # buttons also count as exempt.
        #
        # Logged at INFO with a structured tag — the calibration data this
        # mechanic needs is observable per event, not just per state change.
        if getattr(self, '_joy_sleeping', False) and event.type() in (
            QEvent.MouseButtonPress,
            QEvent.KeyPress,
            QEvent.Wheel,
            QEvent.Enter,
        ):
            exempt = {
                getattr(self, '_sleep_btn', None),
                getattr(self, '_curtains_btn', None),
                getattr(self, '_tray_btn', None),
            }
            exempt.discard(None)
            target = obj
            exempt_hit = None
            depth = 0
            while target is not None and depth < 8:
                if target in exempt:
                    exempt_hit = target
                    break
                try:
                    target = target.parent()
                except RuntimeError:
                    break
                depth += 1
            ev_name = {
                QEvent.MouseButtonPress: "mouse_press",
                QEvent.KeyPress:         "key_press",
                QEvent.Wheel:            "wheel",
                QEvent.Enter:            "enter",
            }.get(event.type(), str(event.type()))
            obj_name = type(obj).__name__ if obj is not None else "None"
            # Side log writer — graceful absence.  The pycache janitor
            # at clean_pycache() unconditionally wipes every *.pyc on
            # the project tree on exit, so a .pyc-based delivery for
            # this module gets removed each cycle.  Until a janitor-
            # compatible binary format is chosen, the import may fail
            # at module load (see top-of-file try/except); when absent,
            # the structured [joy-wake] log line still emits and the
            # rest of the app keeps working.
            if exempt_hit is not None:
                exempt_name = "sleep_btn" if exempt_hit is getattr(self, '_sleep_btn', None) \
                              else "curtains_btn" if exempt_hit is getattr(self, '_curtains_btn', None) \
                              else "tray_btn" if exempt_hit is getattr(self, '_tray_btn', None) \
                              else type(exempt_hit).__name__
                logger.info(
                    "[joy-wake] suppressed event=%s target=%s — exempt via %s",
                    ev_name, obj_name, exempt_name,
                )
                if _joy_narrative is not None:
                    _joy_narrative.record_event(self._joy_narrative_path, ev_name, exempt_name)
            else:
                logger.info(
                    "[joy-wake] WAKE event=%s target=%s",
                    ev_name, obj_name,
                )
                if _joy_narrative is not None:
                    _joy_narrative.record_event(self._joy_narrative_path, ev_name, None)
                self._wake_joy()
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
            pix = self._resolve_registry_icon(entry)
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
        snap.setIcon(QIcon(Theme.icon(Theme.iconPolaroid)))
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

        # Perf instrumentation — capture per-frame timings so we can
        # spot whether resume-lag is bucket-1 (slow first frame =
        # paging / cold cache), bucket-2 (sustained slow = paint
        # pipeline cost), or bucket-3 (stuttery = GC / event flush).
        # Closure pattern: state lives on self._curtain_perf and is
        # finalised in _on_curtains_settled.  curtain_anim is recreated
        # each toggle so the valueChanged connection dies with it; no
        # disconnect bookkeeping needed.
        _now = time.perf_counter()
        gap_s = (
            _now - self._curtain_perf_last_finished_t
            if self._curtain_perf_last_finished_t else None
        )
        self._curtain_perf = {
            "start_t":         _now,
            "prev_frame_t":    _now,
            "deltas_ms":       [],
            "roll":            "up" if collapsing else "down",
            "gap_s":           gap_s,
            "keep_warm_count": self._keep_warm_pulse_count,
        }
        self.curtain_anim.valueChanged.connect(self._on_curtain_frame)
        self.curtain_anim.start()

        self.is_collapsed = not self.is_collapsed

        # Keep-warm timer — runs while curtains are up (collapsed).
        # Ticks DWM via self.update() every _KEEP_WARM_INTERVAL_MS to
        # prevent Bucket 2 cold-pipeline recovery cost on the next
        # rolldown.  Stopped during expanded use where ambient hover
        # pulses already keep the pipeline warm naturally.
        if self.is_collapsed:
            self._keep_warm_timer.start()
        else:
            self._keep_warm_timer.stop()

    def _on_curtain_frame(self, _value) -> None:
        """Per-frame tick for the curtain animation perf hunt.

        Records ms-since-last-frame into self._curtain_perf['deltas_ms'].
        First entry is the gap from .start() to the first valueChanged
        — i.e. Qt animation engine startup cost — which is the most
        likely victim of cold-cache / paging on resume.
        """
        perf = self._curtain_perf
        if perf is None:
            return
        now = time.perf_counter()
        perf["deltas_ms"].append((now - perf["prev_frame_t"]) * 1000.0)
        perf["prev_frame_t"] = now

    def _on_keep_warm_tick(self) -> None:
        """Periodic tiny repaint while curtains are up.

        Schedules a single paintEvent via self.update().  DWM picks the
        repaint up and ticks the compositor for this window, which
        (per the Bucket 2 hypothesis) keeps paint pipeline + GPU shader
        + blur kernel caches referenced and warm.  The visual cost is
        nil — the strip looks identical before and after the repaint;
        only DWM internal state differs.

        Counter increments each tick; the next [curtains-perf] log
        line emits keep_warm=N so the data tells us whether the
        mitigation prevented the Bucket 2 recovery cost.

        See Documents/Compliance/Curtain Resume Lag Investigation.md
        for the diagnostic record this remediation tests.
        """
        self._keep_warm_pulse_count += 1
        self.update()
        logger.debug(
            "[keep-warm] pulse #%d (curtains up, interval=%ds)",
            self._keep_warm_pulse_count,
            self._KEEP_WARM_INTERVAL_MS // 1000,
        )

    def _register_session_notification(self) -> None:
        """Hook into Windows session lock/unlock events.

        WTSRegisterSessionNotification subscribes this window's HWND to
        WM_WTSSESSION_CHANGE messages, which are delivered via the
        normal Win32 message pump — caught by nativeEvent() below.
        Registration is per-HWND, so if the HWND ever gets recreated
        (setWindowFlags, etc.) we'd need to re-register; for now,
        single registration at startup is sufficient.
        """
        try:
            import ctypes
            hwnd = int(self.winId())
            wtsapi = ctypes.windll.wtsapi32
            ok = wtsapi.WTSRegisterSessionNotification(
                ctypes.c_void_p(hwnd), 0  # 0 = NOTIFY_FOR_THIS_SESSION
            )
            if ok:
                logger.debug("[session] registered for lock/unlock events")
            else:
                logger.warning("[session] WTSRegisterSessionNotification returned 0")
        except Exception:
            logger.warning("[session] registration failed", exc_info=True)

    def nativeEvent(self, eventType, message):
        """Catch Windows session change messages for lock/unlock detection.

        Returns (False, 0) for events we don't consume — Qt continues
        normal dispatch.  Only WM_WTSSESSION_CHANGE messages are
        peeked at; everything else passes through untouched.
        """
        try:
            if eventType == b"windows_generic_MSG" or eventType == "windows_generic_MSG":
                import ctypes
                from ctypes import wintypes
                class _MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd",    wintypes.HWND),
                        ("message", wintypes.UINT),
                        ("wParam",  wintypes.WPARAM),
                        ("lParam",  wintypes.LPARAM),
                        ("time",    wintypes.DWORD),
                        ("pt_x",    wintypes.LONG),
                        ("pt_y",    wintypes.LONG),
                    ]
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == self._WM_WTSSESSION_CHANGE:
                    if msg.wParam == self._WTS_SESSION_LOCK:
                        self._is_locked = True
                        self._last_lock_t = time.perf_counter()
                        logger.info("[session] LOCK")
                    elif msg.wParam == self._WTS_SESSION_UNLOCK:
                        self._is_locked = False
                        self._last_unlock_t = time.perf_counter()
                        logger.info("[session] UNLOCK")
        except Exception:
            logger.debug("[session] nativeEvent handler error", exc_info=True)
        return False, 0

    @staticmethod
    def _process_rss_mb() -> float:
        """Resident set size of the current process in MB.

        Uses ctypes against psapi.GetProcessMemoryInfo on Windows — no
        psutil dependency, works in frozen builds, returns 0.0 on any
        failure (this is a metric, not a contract; the heartbeat row
        still writes with rss_mb=0 if the call fails).

        Note: argtypes / restype are load-bearing.  Without them ctypes
        defaults the HANDLE return to int32, which truncates the 64-bit
        pseudo-handle on 64-bit Python and the GetProcessMemoryInfo
        call silently fails.  Use c_void_p so the full handle survives.
        """
        try:
            import ctypes
            from ctypes import c_size_t, c_void_p, c_uint32, byref, sizeof, windll

            class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb",                         c_uint32),
                    ("PageFaultCount",             c_uint32),
                    ("PeakWorkingSetSize",         c_size_t),
                    ("WorkingSetSize",             c_size_t),
                    ("QuotaPeakPagedPoolUsage",    c_size_t),
                    ("QuotaPagedPoolUsage",        c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", c_size_t),
                    ("QuotaNonPagedPoolUsage",     c_size_t),
                    ("PagefileUsage",              c_size_t),
                    ("PeakPagefileUsage",          c_size_t),
                    ("PrivateUsage",               c_size_t),
                ]

            get_proc = windll.kernel32.GetCurrentProcess
            get_proc.argtypes = []
            get_proc.restype = c_void_p

            gpmi = windll.psapi.GetProcessMemoryInfo
            gpmi.argtypes = [c_void_p, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS_EX), c_uint32]
            gpmi.restype = ctypes.c_int

            counters = _PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = sizeof(counters)
            ok = gpmi(get_proc(), byref(counters), counters.cb)
            if not ok:
                return 0.0
            return counters.WorkingSetSize / (1024.0 * 1024.0)
        except Exception:
            return 0.0

    _PERF_LOG_ROTATE_BYTES = 10 * 1024 * 1024  # 10 MB threshold per file

    def _rotate_perf_logs_if_oversized(self) -> None:
        """At startup, archive any perf log file over the size threshold.

        Permanent observability infrastructure: the heartbeat CSV and
        scene-breakdown JSONL grow linearly forever otherwise.  Bound
        the working file at ~10 MB by renaming it with a timestamp
        suffix when over threshold, and starting a fresh file on next
        write.  Archived files are retained — they're the historical
        record for perf analysis — but live in the same Documents/Data/
        directory under their archived name.

        Rotation happens only at startup, never mid-session.  A single
        session never grows past the threshold by enough to matter
        (several MB max for an active day), and avoiding mid-session
        rotation keeps the live writer simple.
        """
        import datetime as _dt
        suffix = _dt.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
        for path in (self._perf_csv_path, self._scene_breakdown_path):
            try:
                if path.exists() and path.stat().st_size > self._PERF_LOG_ROTATE_BYTES:
                    archived = path.with_name(f"{path.stem}-{suffix}{path.suffix}")
                    path.rename(archived)
                    logger.info(
                        "[perf-heartbeat] rotated %s → %s (was %.1f MB)",
                        path.name, archived.name,
                        path.stat().st_size / (1024 * 1024) if path.exists() else 0,
                    )
            except OSError:
                logger.debug("[perf-heartbeat] rotation failed for %s", path, exc_info=True)

    def _on_perf_heartbeat(self) -> None:
        """Phase 2 perf heartbeat tick — write one CSV row.

        Each row captures: timestamp, RSS in MB, GC counts (gen 0/1/2),
        scene item count, curtain state (collapsed/expanded), and the
        seconds-since-previous-tick (heartbeat_gap_s).  The gap column
        is the natural wake signal — a value much larger than the 60 s
        interval indicates the timer paused (system slept / locked /
        was suspended) and just resumed.

        CSV is append-only at Documents/Data/curtain_perf.csv so data
        accumulates across restarts.  The header row is written if the
        file doesn't exist; subsequent runs just append.

        Failures here are caught and logged at debug level — the
        heartbeat is a measurement, not a contract.  A failed heartbeat
        leaves the rest of the app untouched.
        """
        import time as _time
        import gc as _gc
        import datetime as _dt
        try:
            now = _time.perf_counter()
            gap_s = now - self._perf_last_heartbeat_t
            # Flag this tick as a post-wake landing if the gap is well
            # above the configured interval (>= 2× = clear pause signal).
            if gap_s >= 2.0 * (self._PERF_HEARTBEAT_INTERVAL_MS / 1000.0):
                self._perf_last_large_gap_t = now
            self._perf_last_heartbeat_t = now

            rss_mb = self._process_rss_mb()
            g0, g1, g2 = _gc.get_count()
            scene_items = -1
            items_breakdown: dict = {}
            try:
                if getattr(self, 'scene', None):
                    items = self.scene.items()
                    scene_items = len(items)
                    # Categorize by class name — the leak hunt needs
                    # to know WHICH class is fluctuating, not just the
                    # aggregate count.  Bounded by Python's class
                    # vocabulary so the dict size stays small.
                    for it in items:
                        try:
                            k = type(it).__name__
                        except Exception:
                            k = "?"
                        items_breakdown[k] = items_breakdown.get(k, 0) + 1
            except Exception:
                scene_items = -1
            curtain_state = "collapsed" if getattr(self, 'is_collapsed', False) else "expanded"
            ts = _dt.datetime.now().isoformat(timespec='seconds')

            # Ensure parent dir + header on first write
            try:
                self._perf_csv_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            need_header = not self._perf_csv_path.exists()
            with open(self._perf_csv_path, 'a', encoding='utf-8', newline='') as f:
                if need_header:
                    f.write("timestamp,rss_mb,gc_g0,gc_g1,gc_g2,scene_items,curtain_state,heartbeat_gap_s\n")
                f.write(
                    f"{ts},{rss_mb:.1f},{g0},{g1},{g2},{scene_items},"
                    f"{curtain_state},{gap_s:.1f}\n"
                )

            # Write the categorized breakdown to the side log.  JSONL
            # so each line is independently parseable.  Dict insertion
            # is sorted at serialise-time so the same set of types
            # always serialises in the same column order — easy to
            # diff between consecutive lines visually.
            try:
                import json as _json
                row = {"ts": ts}
                for k in sorted(items_breakdown.keys()):
                    row[k] = items_breakdown[k]
                with open(self._scene_breakdown_path, 'a', encoding='utf-8', newline='') as f:
                    f.write(_json.dumps(row, separators=(',', ':')) + "\n")
            except Exception:
                pass
        except Exception:
            logger.debug("[perf-heartbeat] tick write failed", exc_info=True)

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

        # ── Curtain perf summary ─────────────────────────────────────────────
        # Digest the per-frame deltas into one log line per curtain.
        # Reading the shape:
        #   - first ≫ median  → bucket-1 (cold cache / paging on first frame)
        #   - median ≈ max ≫ ideal → bucket-2 (sustained paint pipeline cost)
        #   - max isolated, median fine → bucket-3 (intermittent GC / event flush)
        # The 'gap' field is seconds since the previous curtain settled —
        # a long gap (>300s) flags this run as post-idle.
        perf = self._curtain_perf
        if perf and perf["deltas_ms"]:
            deltas = perf["deltas_ms"]
            n = len(deltas)
            sorted_d = sorted(deltas)
            total_ms  = (time.perf_counter() - perf["start_t"]) * 1000.0
            first_ms  = deltas[0]
            median_ms = sorted_d[n // 2]
            p95_ms    = sorted_d[min(n - 1, int(n * 0.95))]
            max_ms    = sorted_d[-1]
            gap = perf["gap_s"]
            gap_str = f"{gap:.0f}s" if gap is not None else "first-curtain"
            # since_wake = seconds since the most recent post-wake landing
            # (heartbeat tick that came in after a multi-interval gap).
            # Distinguishes "first click after wake" (small value) from
            # "click after warming up with other activity" (large value).
            # Reports "—" if no post-wake landing has been observed in
            # this session, i.e. the app was running uninterrupted.
            now_t = time.perf_counter()
            if self._perf_last_large_gap_t > 0.0:
                since_wake_s = now_t - self._perf_last_large_gap_t
                since_wake_str = f"{since_wake_s:.0f}s"
            else:
                since_wake_str = "—"
            # since_unlock: time since the most recent observed Windows
            # unlock event.  "—" if no unlock has been observed in this
            # session (i.e. screen has been continuously unlocked since
            # the app started).  Captures the lock-state variable
            # without controlled experiments.
            if self._last_unlock_t > 0.0:
                since_unlock_str = f"{(now_t - self._last_unlock_t):.0f}s"
            else:
                since_unlock_str = "—"
            logger.info(
                "[curtains-perf] roll=%s total=%.0fms | gap=%s | keep_warm=%d | "
                "since_wake=%s | since_unlock=%s | frames=%d | "
                "first=%.0fms median=%.0fms p95=%.0fms max=%.0fms",
                perf["roll"], total_ms, gap_str, perf["keep_warm_count"],
                since_wake_str, since_unlock_str, n,
                first_ms, median_ms, p95_ms, max_ms,
            )
        self._curtain_perf_last_finished_t = time.perf_counter()
        self._curtain_perf = None
        # Reset for the next gap — the keep-warm timer will accumulate
        # again from zero across the upcoming idle period.
        self._keep_warm_pulse_count = 0


    def _get_dock_offsets(self) -> dict:
        """Read app-specific dock offsets from settings.toml [intricate.dock_offsets].

        Each key is a lowercase exe name, value is the Y offset in px from screen top.
        Only apps listed here are eligible for dock snapping — unlisted apps are ignored.

        Example settings.toml entry:
            [intricate.dock_offsets]
            "claude.exe" = 0
            "chrome.exe" = 50
        """
        import shared_braincell.settings as _s
        return _s.get("intricate", "dock_offsets", default={})

    def _toggle_dock_position(self) -> None:
        """Glide the rolled-up strip to a Y position based on the app behind it."""
        if not self.is_collapsed:
            return
        from shared_braincell import get_window_behind
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
        from shared_braincell import get_window_behind
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
        _sidebar_template = "background-color: {bg};"
        sidebar.setStyleSheet(_sidebar_template.format(bg=Theme.windowBg))
        self._chrome_pulse_targets.append((sidebar, _sidebar_template))

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
        _cat_btn(Theme.iconPolaroid,     "Images", self._show_images_menu)
        _cat_btn(Theme.iconAudioGroup,   "Audio",  self._show_audio_menu)
        _cat_btn(Theme.iconVisualGroup,  "Visual", self._show_visual_menu)
        _cat_btn(Theme.iconHealthGroup,  "Health", self._show_health_menu)
        _cat_btn(Theme.iconToolsGroup,   "Tools",  self._show_tools_menu)
        _cat_btn(Theme.iconInfoGroup,    "Info",   self._show_info_menu)
        # Adobe category sits between Info and Claude so the letterform trio
        # at the bottom of the sidebar reads cleanly top→down: A (Adobe) →
        # i (Info, just above) → Ai (Anthropic, just below).
        # scale=1.0 matches the Anthropic treatment — brand silhouettes fill
        # their bounding box natively and don't need the 1.28× padding
        # compensation the ringed line-art family uses.
        _cat_btn(Theme.iconAdobeGroup,   "Adobe",  self._show_adobe_menu, scale=1.0)
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
        #   sliders row   → reserved (col 1), zoom (col 2), blur (col 3)
        #   progress row  → reserved (col 1), reserved (col 2), joy (col 3)
        # Reserved slots use fixed-size spacers so column alignment is
        # preserved before the future peers land.
        import shared_braincell.settings as _s
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
        # Reserved column to the LEFT of the zoom slider keeps zoom centred.
        sliders_row_layout.addSpacerItem(_reserved_slot())

        # Zoom slider — moved from the bottom toolbar to live with its peers.
        # Slider position 0-1000 maps to zoom 0.03-5.0 via a two-segment
        # cubic Hermite curve stitched at the pivot (1.0× zoom). Slope is
        # continuous at the join — Bezier-smooth, no piecewise kinks.
        # See _slider_pos_to_zoom for the curve knobs.
        self._zoom_slider = pretty_slider(
            Qt.Vertical,
            handle_icon="slider_handle_vertical.png",
            handle_size=28,
            range=(0, 1000),
            value=600,
            invertedAppearance=False,
            fixedWidth=bar_width,
            minimumHeight=bar_min_height,
            singleStep=10,
            pageStep=50,
            valueChanged=self._on_zoom_slider,
        )
        sliders_row_layout.addWidget(self._zoom_slider)

        # Blur slider — drives the backdrop opacity layer. Now to the RIGHT
        # of the zoom slider so the zoom stays in the centre column.
        sliders_row_layout.addWidget(self.blur_slider)

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
        from joy import joy_state as _joy_state
        self.joy_bar.setValue(_joy_state.load()["bar_value"])
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
        # Bucket count has its own tiny file store (joy/joy_buckets.py) —
        # detached from settings.toml so the value can be tweaked by hand
        # without touching the shared-braincell config surface. A watcher
        # picks up external edits live so hand-tweaks don't get clobbered
        # by the next _persist_happy tick.
        from joy import joy_buckets
        from joy import joy_state as _joy_state
        self._joy_bucket_count = joy_buckets.get_buckets()
        self._joy_buckets_watcher = joy_buckets.JoyBucketsWatcher(self)
        self._joy_buckets_watcher.changed.connect(self._on_joy_buckets_external_change)
        self._joy_happy_secs   = _joy_state.load()["happy_secs"]
        # Live external-edit pickup for joy_state.json — Settlers writes
        # bar-value overrides through this watcher, no restart needed.
        self._joy_state_watcher = _joy_state.JoyStateWatcher(self)
        self._joy_state_watcher.changed.connect(self._on_joy_state_external_change)
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

        # Feed rate limits — three layers:
        #   1) per-feed cooldown (FEED_COOLDOWN) — minimum interval between
        #      individual feeds.  Original draft note: "you can't just keep
        #      eating to get happier."  Without this the user could spam-
        #      click the feed button 3 times in a second to fill the bar,
        #      which doesn't match how feeding actually works.  Cooldown
        #      simulates the cat digesting between bites.
        #   2) rolling window cap (FEED_MAX in FEED_WINDOW) — total
        #      stuffed-ness across a longer span so the user can't chain
        #      feeds-with-cooldown-respected indefinitely.
        #   3) bar full (>= 100) — can't eat any more right now.
        # FEED_WINDOW and FEED_COOLDOWN both SCALE with awake-drain-minutes
        # so the feeding cadence matches the hunger cadence at any setting:
        # the original tuning is 60-min drain ↔ 10-min window ↔ 1-min
        # cooldown, and those ratios are the actual design target.  Live
        # values are set in _apply_joy_settings (called immediately below
        # at __init__ and again on every settings.toml change).  The
        # placeholders here cover only the construction-time window
        # before _apply_joy_settings runs.
        self._feed_timestamps: list[float] = []
        self._FEED_WINDOW    = 600.0      # placeholder; set by _apply_joy_settings
        self._FEED_COOLDOWN  = 60.0       # placeholder; set by _apply_joy_settings
        self._FEED_MAX       = 3          # meals allowed per window
        self._last_feed_time = 0.0        # for per-feed cooldown

        # Restore feed cadence state from joy_state.json so the cooldown
        # survives an app restart.  The "feed once at low → restart to
        # bypass cooldown → feed again" workaround was the path of least
        # resistance until the joy_mood Phase 2 stomach-pouch mechanic
        # made the swallow-gap meaningful — closing the workaround is a
        # prerequisite for that mechanic to be honest.  Stored in wall-
        # clock; converted back to current monotonic frame here.
        _saved = _joy_state.load()
        _wall_now = time.time()
        _mono_now = time.monotonic()
        for _wall_t in _saved.get("feed_wall_times", []):
            _elapsed = _wall_now - _wall_t
            # Drop entries with negative elapsed (clock skew / NTP correction)
            # or outside the rolling window (already irrelevant to cap check).
            if 0 <= _elapsed < self._FEED_WINDOW:
                self._feed_timestamps.append(_mono_now - _elapsed)
        _last_feed_wall = _saved.get("last_feed_wall", 0.0)
        if _last_feed_wall > 0:
            _elapsed = _wall_now - _last_feed_wall
            if _elapsed >= 0:
                self._last_feed_time = _mono_now - _elapsed

        # Depletion timer + happy accumulator. The four tunable knobs
        # below — drain durations, grace window, bucket earn rate — are
        # read from [intricate.joy] in settings.toml at startup AND on
        # every settings change (live-reload through The Settlers).
        # _apply_joy_settings() is the single source of truth for both
        # the initial seed and runtime updates.
        self._joy_hungry = False          # dirty flag — cleared by any feed click
        self._joy_sleeping = False        # sleep mode — slower depletion
        self._joy_timer = QTimer(self)
        self._joy_timer.timeout.connect(self._deplete_joy)
        self._joy_grace_remaining = 0.0   # seconds left in current grace window
        self._joy_in_grace        = False  # True while bar is 100% and grace active
        self._happy_persist_tick  = 0      # modulo-30 counter for periodic save —
                                            # decoupled from happy_secs value because
                                            # depletion makes the value non-integer
        self._happy_timer = QTimer(self)
        self._happy_timer.setInterval(1000)  # 1-second resolution
        self._happy_timer.timeout.connect(self._tick_happy)
        # Seed _JOY_* constants + timer interval from settings.toml.
        self._apply_joy_settings()
        # Wake-decay — the app being closed is the app being asleep, same
        # framing as human hunger slowing down while not active. Compute
        # elapsed seconds since the saved last_active_at and apply the
        # configured sleep-rate decay to the loaded bar value before the
        # depletion timer starts running. Has to land AFTER _apply_joy_settings
        # so _JOY_SLEEP_INTERVAL is populated, BEFORE the timer starts so the
        # tick doesn't overlap with the decay write. See _apply_sleep_decay_on_wake.
        self._apply_sleep_decay_on_wake()
        self._joy_timer.start()

        # If we launch at 100%, start the grace immediately.  Otherwise
        # start the happy timer for depletion — it now runs continuously
        # while awake regardless of bar value (grow-in-grace, decay-out-
        # of-grace).  Sleep-mode pauses it; wake resumes.
        if self.joy_bar.value() == 100:
            self._begin_grace()
        else:
            self._happy_timer.start()

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
        import shared_braincell.settings as _s
        _s.set_nested("intricate", "canvas", "blur_alpha", value)

    def _on_feed_pressed(self) -> None:
        """Mouse down — ShadowStickerButton handles the depth shift visually."""
        pass

    def _on_feed_released(self) -> None:
        """Mouse up — trigger the feed action."""
        self._feed_joy()

    def _feed_joy(self) -> None:
        """Feed the joy bucket — any click resets the timer and clears hunger.

        Three-layer rate limit (see _FEED_* docs in __init__):
          1. Bar already full → silent no-op (can't eat more right now).
          2. Inside per-feed cooldown → silent no-op (still digesting).
          3. Window cap reached → silent no-op (stuffed for now).
        Each layer is also reflected in the feed button's enabled state
        via _refresh_feed_btn_state, so the user gets visible feedback
        instead of a clicking-and-nothing-happens silence.
        """
        # Already full — didn't eat anything, don't count it
        if self.joy_bar.value() >= 100:
            self._refresh_feed_btn_state()
            return

        now = time.monotonic()

        # Per-feed cooldown — "you can't just keep eating to get happier"
        if now - self._last_feed_time < self._FEED_COOLDOWN:
            self._refresh_feed_btn_state()
            return

        # Prune timestamps outside the window, then check the rolling cap
        self._feed_timestamps = [
            t for t in self._feed_timestamps
            if now - t < self._FEED_WINDOW
        ]
        if len(self._feed_timestamps) >= self._FEED_MAX:
            self._refresh_feed_btn_state()
            return                        # stuffed — can't eat any more right now

        self._feed_timestamps.append(now)
        self._last_feed_time = now
        v = min(100, self.joy_bar.value() + 10)
        self.joy_bar.setValue(v)
        # Going from hungry → fed: stop the chrome pulse so the whole-app
        # background returns to its dark resting state.  Idempotent if the
        # pulse wasn't running.
        was_hungry = self._joy_hungry
        self._joy_hungry = False
        if was_hungry:
            self._stop_chrome_pulse()
        # Reset the depletion timer so feeding buys a full cycle of peace
        if hasattr(self, '_joy_timer') and self._joy_timer.isActive():
            self._joy_timer.start()
        # If we just hit 100%, start the grace period (happy time begins)
        if v == 100 and not self._joy_in_grace:
            self._begin_grace()
        self._refresh_feed_btn_state()

    def _refresh_feed_btn_state(self) -> None:
        """Update the feed button's enabled state and schedule the next
        refresh if currently locked.  Locks fire when:
          - bar is at 100 % (full, can't eat more — unlocks on next drain)
          - per-feed cooldown is active (still digesting)
          - rolling window cap is reached (stuffed for the window's tail)
        Auto-reschedules itself at the soonest unlock event so the button
        comes back to life on its own without the caller having to track
        the timing explicitly.

        Also: when a *digestion* lock (cooldown or window cap) lifts, fire
        a meov reminder — the cat finished her digestion beat and is
        asking for the next bite.  The "full → not full" transition does
        NOT fire one; that one is just the bar drifting back into edible
        territory while the cat is still content, not the cat asking.
        """
        if not hasattr(self, '_feed_btn'):
            return
        now = time.monotonic()
        # Prune expired window entries while we're here so the cap check
        # below operates on fresh state.
        self._feed_timestamps = [
            t for t in self._feed_timestamps
            if now - t < self._FEED_WINDOW
        ]
        full = self.joy_bar.value() >= 100
        cooldown_active = (now - self._last_feed_time) < self._FEED_COOLDOWN
        cooldown_remaining = max(0.0, self._FEED_COOLDOWN - (now - self._last_feed_time))
        window_cap_active = len(self._feed_timestamps) >= self._FEED_MAX
        if window_cap_active:
            window_remaining = max(0.0, self._FEED_WINDOW - (now - min(self._feed_timestamps)))
        else:
            window_remaining = 0.0

        locked = full or cooldown_active or window_cap_active
        try:
            self._feed_btn.setEnabled(not locked)
        except RuntimeError:
            return  # button torn down

        # Detect a digestion-lock → unlock transition and fire a feed-
        # availability meov.  Compare against the *previous* lock state
        # snapshot so we only catch the falling edge, not every tick that
        # happens to find both flags clear.  Skip when the bar is full —
        # the cat isn't asking for food while she's already stuffed,
        # only after she's both finished digesting AND has some appetite
        # available.
        prev_cooldown = getattr(self, '_feed_btn_prev_cooldown', False)
        prev_window   = getattr(self, '_feed_btn_prev_window_cap', False)
        digestion_just_lifted = (
            (prev_cooldown and not cooldown_active)
            or (prev_window and not window_cap_active)
        )
        if digestion_just_lifted and not full:
            # _meov_tick handles the typewriter whisper, the colour pulse,
            # the dot escalation, and the click-to-acknowledge wire — the
            # whole meov channel reused for the "ready for the next bite"
            # reminder so it reads as a sibling of the other meov beats
            # rather than a separate alert system.
            self._meov_tick()
        self._feed_btn_prev_cooldown   = cooldown_active
        self._feed_btn_prev_window_cap = window_cap_active

        # Re-schedule next refresh at the soonest auto-unlock event.  Skip
        # the "full" lock — that one unlocks when the depletion timer ticks
        # the bar below 100, which calls _refresh_feed_btn_state on its
        # own at the end of _deplete_joy.
        if not locked:
            return
        unlock_in = []
        if cooldown_remaining > 0:
            unlock_in.append(cooldown_remaining)
        if window_remaining > 0:
            unlock_in.append(window_remaining)
        if unlock_in:
            QTimer.singleShot(
                int(min(unlock_in) * 1000) + 50,
                self._refresh_feed_btn_state,
            )

    def _toggle_joy_sleep(self) -> None:
        """Put the joy system to sleep or wake it up."""
        if self._joy_sleeping:
            self._wake_joy()
        else:
            self._sleep_joy()

    def _sleep_joy(self) -> None:
        """Enter sleep mode — slow depletion, muted meows.

        Pauses the happy timer too; the cat is at rest, the relationship
        clock pauses with her.  Both growth (during a grace window that
        happened to be active) and decay (everywhere else) freeze.
        """
        self._joy_sleeping = True
        self._joy_timer.setInterval(self._JOY_SLEEP_INTERVAL)
        self._joy_timer.start()          # restart with new interval
        self._happy_timer.stop()         # freeze grow/decay while asleep
        self._sleep_btn.setIcon(QIcon(Theme.icon(Theme.iconSleepingIconic, fallback_color="#9a7abf")))
        self._sleep_btn.setToolTip("Wake me up")

    def _wake_joy(self) -> None:
        """Exit sleep mode — normal depletion resumes.

        Restarts the happy timer so grow/decay resumes from the value
        held at sleep entry.  No catch-up integration over the slept
        period — the relationship clock paused, no time accrued or lost.
        """
        if not self._joy_sleeping:
            return
        self._joy_sleeping = False
        self._joy_timer.setInterval(self._JOY_AWAKE_INTERVAL)
        self._joy_timer.start()          # restart with new interval
        if not self._happy_timer.isActive():
            self._happy_timer.start()    # resume grow/decay
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
        if not self._happy_timer.isActive():
            self._happy_timer.start()

    def _end_grace(self) -> None:
        """Grace expired — happy now decays gently until bar returns to 100%.

        The timer keeps running; the next tick lands in the depletion
        branch instead of the growth branch.  Stopping the timer would
        freeze happy_secs at its current value, which is the original
        bug this change fixes.
        """
        self._joy_in_grace = False

    def _tick_happy(self) -> None:
        """One-second pulse driving the happy accumulator.

        Two branches:
          - in grace (bar at 100% within the grace window) → grow
          - awake outside grace → decay toward zero

        Sleep mode pauses both branches by stopping the timer in
        _sleep_joy.  A stray tick that lands after the stop is guarded
        below.

        Decay is linear at _JOY_HAPPY_DEPLETION_PER_SEC, floored at 0.
        See joy/joy_mood.py for the richer model (intensity-modulated
        decay, tri-state, NPC layer) that replaces this at wire-in time.
        """
        # Stray-tick guard — _sleep_joy stops the timer, but a tick can
        # already be queued.
        if self._joy_sleeping:
            return

        if self._joy_in_grace:
            if self.joy_bar.value() < 100:
                # Bar dropped mid-grace (rare; external edit, etc.).
                # Clear grace and let the next tick handle decay.
                self._end_grace()
                self._joy_grace_remaining = 0.0
            else:
                # Growth branch
                self._joy_happy_secs += 1.0
                if self._joy_happy_secs >= self._JOY_BUCKET_SECS:
                    self._joy_happy_secs -= self._JOY_BUCKET_SECS
                    # Bump via the store so the file is the authoritative
                    # source (no in-memory drift from concurrent external
                    # edits).
                    self._joy_bucket_count = joy_buckets.bump_buckets(1)
                    self._joy_bucket_label.setText(str(self._joy_bucket_count))
                    self._persist_happy()
                self._joy_grace_remaining -= 1.0
                if self._joy_grace_remaining <= 0:
                    self._end_grace()
        else:
            # Decay branch — gentle linear depletion outside grace.
            # Floors at 0; permanence holds the relationship at the
            # zero floor, never below.
            if self._joy_happy_secs > 0.0:
                self._joy_happy_secs = max(
                    0.0,
                    self._joy_happy_secs - self._JOY_HAPPY_DEPLETION_PER_SEC,
                )

        # Tooltip refresh (both branches) — live progress for the bucket
        # label hover.
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())

        # Periodic persist — modulo a tick counter rather than the
        # happy_secs value, since depletion makes happy non-integer and
        # the old `int(...) % 30 == 0` check wouldn't fire reliably.
        self._happy_persist_tick = (self._happy_persist_tick + 1) % 30
        if self._happy_persist_tick == 0:
            self._persist_happy()

    # ── Joy mechanic tunables ─────────────────────────────────────────────
    # Defaults match the original hardcoded constants — preserved as fall-
    # backs so a missing or malformed TOML key never breaks the mechanic.
    _JOY_DEFAULTS = {
        "awake_drain_minutes": 60,    # bar 100→0 over 1 hour awake
        "sleep_drain_minutes": 600,   # bar 100→0 over 10 hours asleep
        "grace_secs":          600,   # 10 min grace at 100% before drain starts
        "bucket_minutes":      60,    # 1 hour of happy time earns 1 bucket
        "happy_drain_minutes": 600,   # happy 3600s→0 over 10 hours outside grace
    }

    def _apply_joy_settings(self) -> None:
        """Read [intricate.joy] tunables from settings.toml and apply them
        live. Called on init and again every time settings.toml changes
        (Settlers writes through, watcher fires, this re-reads).

        The Settlers exposes the values in user-friendly units; we convert
        to internal ms-per-tick / seconds here so the rest of the joy code
        stays unaware of the user-facing unit choice.

        Idempotent: calling this with unchanged TOML produces no behavioural
        change. Calling with new values updates the depletion timer's
        interval (via setInterval, which Qt handles cleanly even mid-run).
        """
        import shared_braincell.settings as _s

        d = self._JOY_DEFAULTS
        awake_min = int(_s.get_nested("intricate", "joy", "awake_drain_minutes", d["awake_drain_minutes"]))
        sleep_min = int(_s.get_nested("intricate", "joy", "sleep_drain_minutes", d["sleep_drain_minutes"]))
        grace_s   = int(_s.get_nested("intricate", "joy", "grace_secs",          d["grace_secs"]))
        bucket_m  = int(_s.get_nested("intricate", "joy", "bucket_minutes",      d["bucket_minutes"]))
        happy_min = int(_s.get_nested("intricate", "joy", "happy_drain_minutes", d["happy_drain_minutes"]))

        # Bar drains in 100 ticks of 1 unit each; total drain time = ticks ×
        # interval. interval_ms = (minutes * 60 * 1000) / 100 = minutes * 600.
        self._JOY_AWAKE_INTERVAL = max(1, awake_min) * 600
        self._JOY_SLEEP_INTERVAL = max(1, sleep_min) * 600
        self._JOY_GRACE_SECS     = max(0, grace_s)
        self._JOY_BUCKET_SECS    = max(60, bucket_m * 60)   # floor of 1 minute

        # Happy depletion rate while awake and outside grace.  Linear decay
        # toward zero — floor at 0 because Intricate's permanence is
        # unconditionally True (see joy/joy_mood.py for the richer model
        # that this simple constant will be replaced by at wire-in time).
        # Default: 3600 s → 0 over 600 minutes = 0.1 happy-sec per real-sec.
        self._JOY_HAPPY_DEPLETION_PER_SEC = (
            self._JOY_BUCKET_SECS / (max(1, happy_min) * 60.0)
        )

        # Feed window scales with drain rate to preserve the 1:6 design
        # ratio (60-min drain ↔ 600 s feed window).  Without this the user
        # tuning awake_drain_minutes down for testing finds the cat going
        # hungry before the feed cooldown can clear — feeds-per-window
        # stays at 3 but the time available to use them shrinks with the
        # drain.  Floor at 5 s so absurdly fast drains don't make the
        # window unusably small.
        self._FEED_WINDOW = max(5.0, max(1, awake_min) * 60.0 / 6.0)

        # Per-feed cooldown — minimum interval between individual feeds.
        # Scales as window/10 so the original 60-min ↔ 10-min-window ↔
        # 1-min-cooldown ratio holds across all drain settings:
        #   60-min drain → window 600s → cooldown 60s
        #   30-min drain → window 300s → cooldown 30s
        #   10-min drain → window 100s → cooldown 10s
        #    3-min drain → window  30s → cooldown  3s
        # Floor of 1.5 s so very fast drains still register a perceptible
        # "she's still digesting" beat without becoming click-spammable.
        self._FEED_COOLDOWN = max(1.5, self._FEED_WINDOW / 10.0)

        # Apply to the running depletion timer. setInterval is safe mid-run
        # — Qt re-arms on the next tick. Pick the right interval for the
        # current sleep/awake mode so live-tuning the awake timer takes
        # effect even while sleeping (and vice versa).
        if hasattr(self, '_joy_timer'):
            target_interval = (
                self._JOY_SLEEP_INTERVAL if self._joy_sleeping
                else self._JOY_AWAKE_INTERVAL
            )
            if self._joy_timer.interval() != target_interval:
                self._joy_timer.setInterval(target_interval)
                logger.debug(
                    "[joy-tune] timer interval re-applied → %d ms (%s)",
                    target_interval, "sleep" if self._joy_sleeping else "awake"
                )

        logger.debug(
            "[joy-tune] applied: awake_drain=%dm sleep_drain=%dm grace=%ds bucket=%dm "
            "happy_drain=%dm (%.4f/s) feed_window=%.1fs feed_cooldown=%.1fs",
            awake_min, sleep_min, grace_s, bucket_m, happy_min,
            self._JOY_HAPPY_DEPLETION_PER_SEC,
            self._FEED_WINDOW, self._FEED_COOLDOWN,
        )

        # Live-tune feedback for the feed button — recompute its enabled
        # state against the new window/cooldown.  Skip silently if the
        # button doesn't exist yet (this method runs once during __init__
        # before the sidebar is built).
        if hasattr(self, '_feed_btn'):
            self._refresh_feed_btn_state()

    def _apply_sleep_decay_on_wake(self) -> None:
        """On launch, decay the bar by the elapsed time since last save.

        The framing: the app being closed is the app being asleep — same
        shape as human hunger when not active. While running awake the
        bar drains at the awake rate (default 1 hr 100→0); while running
        asleep (sidebar sleep button) the bar drains at the sleep rate
        (default 10 hr 100→0). When the app is shut down entirely, that's
        a deeper kind of asleep — but the rate that applies is still the
        configured sleep_drain rate, since "asleep" is a single mode from
        the bar's perspective.

        This makes restarts honest: if the user closed the app last night
        with the bar at 80, opens it the next morning ~10 hours later, the
        bar drains by ~100% over the configured sleep window. The bar
        loads at 0%, super hungry — exactly the user's stated intent for
        wake-up behaviour ("wake up super hungry at 0% even").

        Skipped when:
          - last_active_at is None (cold start, no previous run on record)
          - last_active_at parse fails (corrupted timestamp)
          - elapsed time is negative (clock skew across the close/launch
            boundary, e.g. user changed system time backward)
          - sleep_drain_minutes is 0 or unset (would divide by zero)
        """
        from datetime import datetime
        from joy import joy_state as _joy_state
        import shared_braincell.settings as _s

        state = _joy_state.load()
        saved_ts = state.get("last_active_at")
        if not saved_ts:
            return
        try:
            last_active = datetime.fromisoformat(saved_ts)
        except (ValueError, TypeError):
            logger.debug("[joy] wake-decay: bad last_active_at=%r, skipping", saved_ts)
            return
        elapsed_s = (datetime.now() - last_active).total_seconds()
        if elapsed_s <= 0:
            return

        # Sleep drain in seconds for full 100→0 traversal. Same value the
        # _JOY_SLEEP_INTERVAL is derived from, but read here directly so
        # the decay calc isn't coupled to the timer's per-tick interval
        # representation.
        sleep_drain_min = int(_s.get_nested(
            "intricate", "joy", "sleep_drain_minutes",
            self._JOY_DEFAULTS["sleep_drain_minutes"],
        ))
        sleep_drain_total_s = sleep_drain_min * 60
        if sleep_drain_total_s <= 0:
            return

        drain_pct = (elapsed_s / sleep_drain_total_s) * 100.0
        before = self.joy_bar.value()
        after = max(0, int(round(before - drain_pct)))
        if after < before:
            self.joy_bar.blockSignals(True)
            self.joy_bar.setValue(after)
            self.joy_bar.blockSignals(False)
            logger.info(
                "[joy] wake-decay: bar %d → %d (closed for %.0f sec at sleep rate "
                "of %d min for full drain)",
                before, after, elapsed_s, sleep_drain_min,
            )
        else:
            logger.debug(
                "[joy] wake-decay: bar stays at %d (%.0f sec elapsed, "
                "%.2f%% theoretical drain rounds to 0)",
                before, elapsed_s, drain_pct,
            )

    def _persist_happy(self) -> None:
        """Save happy accumulator, bar value, and feed cadence state to
        the joy_state sidecar.

        Bucket count is NOT written here — it's persisted at earn time
        via joy_buckets.bump_buckets, so the file store is always
        authoritative and external hand-edits are never overwritten by
        a later _persist_happy tick.  Same isolation principle for the
        sidecar pair as for the bucket file: runtime persistence lives
        outside settings.toml so The Settlers' user-tunable surface
        never has to wrestle with values the app writes to itself.

        Feed cadence (timestamps + last_feed_time) is converted from
        the in-memory monotonic frame to wall-clock anchors so the
        cooldown / window-cap state survives across an app restart.
        Closes the "restart-as-feed-bypass" workaround that was the
        path of least resistance before the swallow-gap mechanic in
        joy_mood Phase 2 made it actively harmful to the design.
        """
        from joy import joy_state as _joy_state
        mono_now = time.monotonic()
        wall_now = time.time()
        feed_wall_times = [
            wall_now - (mono_now - t) for t in self._feed_timestamps
        ]
        last_feed_wall = (
            wall_now - (mono_now - self._last_feed_time)
            if self._last_feed_time > 0 else 0.0
        )
        _joy_state.save(
            self._joy_happy_secs,
            self.joy_bar.value(),
            feed_wall_times=feed_wall_times,
            last_feed_wall=last_feed_wall,
        )

    def _on_joy_buckets_external_change(self, new_value: int) -> None:
        """Fired when joy_buckets.txt is edited from outside the running
        process (e.g., hand-tweak from a chat session, or a Settlers
        bucket-override slider). Sync the in-memory count and the label
        so the UI reflects the new value immediately."""
        self._joy_bucket_count = new_value
        self._joy_bucket_label.setText(str(new_value))
        self._joy_bucket_label.setToolTip(self._joy_bucket_tooltip())

    def _on_joy_state_external_change(self, state: dict) -> None:
        """Fired when joy_state.json is edited from outside the running
        process (Settlers bar-value override, or hand-edit). Apply the
        new bar value live and re-seat the happy accumulator. Skip the
        write-back loop — _persist_happy will resave on its own cycle.

        bar_value is the user-visible tuning knob. happy_secs is the
        internal accumulator; we honour an external override of it too
        so the GDC-style 'jump to N seconds toward next bucket' test
        scenario works, but the typical Settlers slider only writes
        bar_value."""
        new_bar = int(state.get("bar_value", self.joy_bar.value()))
        new_secs = float(state.get("happy_secs", self._joy_happy_secs))
        new_grace = state.get("grace_remaining")  # None means "no override"
        # Block the bar's own valueChanged-driven side effects since this
        # write originates externally and shouldn't re-arm grace logic.
        self.joy_bar.blockSignals(True)
        self.joy_bar.setValue(max(0, min(100, new_bar)))
        self.joy_bar.blockSignals(False)
        self._joy_happy_secs = new_secs
        # Fresh full bar should re-arm grace; less than full should clear
        # any grace state so depletion resumes naturally.
        if self.joy_bar.value() == 100 and not self._joy_in_grace:
            self._begin_grace()
        elif self.joy_bar.value() < 100 and self._joy_in_grace:
            self._joy_in_grace = False
            self._joy_grace_remaining = 0.0
            # Don't stop the timer — depletion takes over from next tick.
        # Grace-remaining override — Settlers writes this key when the
        # user wants to fast-forward through grace and watch decay kick
        # in (or extend grace beyond _JOY_GRACE_SECS for testing growth).
        # Applied AFTER the bar/grace flag adjustments above so the
        # override lands on the corrected in_grace state.  Pure value
        # nudge — does not force in_grace=True; if bar < 100 the value
        # sits dormant until next bar→100 begins fresh grace.
        if new_grace is not None:
            self._joy_grace_remaining = max(0.0, float(new_grace))
        # Ensure the happy timer is running for grow/decay.  External
        # writes can land in any state; if the timer was previously off
        # (e.g. legacy session save before depletion landed) start it
        # now so the live value moves.  Sleep mode wins — never start
        # the timer while asleep.
        if not self._joy_sleeping and not self._happy_timer.isActive():
            self._happy_timer.start()
        self.update()

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
        # Flip dirty once below threshold; feeding is the only way back.
        # When joy crosses the threshold she goes hungry — fire a meov tick
        # immediately AND start the whole-app chrome pulse.  The text-meov
        # is the local-attention signal (whisper + titlebar-text pulse);
        # the chrome pulse is the at-distance signal that runs continuously
        # until fed.  Two channels because text fades quickly while the
        # surface pulse is the persistent "she's hungry" register that
        # works even when the user is across the room.
        if v < 15 and not self._joy_hungry:
            self._joy_hungry = True
            self._meov_tick()
            self._start_chrome_pulse()
        # Recompute feed-button enabled state — bar dropping below 100
        # unlocks the "full" gate, this is where that re-enable happens.
        self._refresh_feed_btn_state()

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
            "open_indesign":     self._open_session_indesign,
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

    def _resolve_registry_icon(self, entry: dict) -> "QPixmap":
        """Resolve a registry entry's icon via either field:

          icon_file = "xxx.ico"      — direct filename, used for OS-extracted
                                       app icons that sidestep the Theme
                                       metaclass indirection entirely.
          icon      = "iconXxx"      — logical name resolved via Theme's
                                       metaclass lookup into settings.toml.

        icon_file wins when both are present.  Either way, icon_fallback
        controls the sentinel color shown when the file is missing.
        """
        fallback = entry.get("icon_fallback", "#6b5a47")
        icon_file = entry.get("icon_file")
        if icon_file:
            return Theme.icon(icon_file, fallback_color=fallback)
        icon_attr = entry.get("icon", "")
        icon_val = getattr(Theme, icon_attr, None)
        return Theme.icon(icon_val, fallback_color=fallback) if icon_val else Theme.icon(None)

    def _show_category_menu(self, category: str, btn: QPushButton) -> None:
        """Build a category menu from node_registry.toml entries."""
        from utils.persistence import registry

        self._ensure_dispatch()
        menu = self._styled_menu()

        # Non-node actions first (e.g. Restore, Snip in tools)
        for key, entry in registry.get_actions_by_category(category):
            pix = self._resolve_registry_icon(entry)
            act = menu.addAction(QIcon(pix), entry.get("name", key))
            tip = entry.get("tooltip", "")
            if tip:
                act.setToolTip(tip)
            handler = self._action_dispatch.get(key)
            if handler:
                act.triggered.connect(handler)

        # Node entries
        for key, entry in registry.get_nodes_by_category(category):
            pix = self._resolve_registry_icon(entry)
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
    def _show_adobe_menu(self, btn):   self._show_category_menu("adobe", btn)
    def _show_info_menu(self, btn):
        """Info menu: registry entries + dynamic Documents/*.md files."""
        from pathlib import Path
        from utils.persistence import registry

        self._ensure_dispatch()
        menu = self._styled_menu()

        # Registry-driven entries (same as _show_category_menu)
        for key, entry in registry.get_nodes_by_category("info"):
            pix = self._resolve_registry_icon(entry)
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

    def _open_session_indesign(self) -> None:
        """Open the current session's default InDesign file via the OS handler.

        Convention: each project folder keeps its Adobe sources in a sibling
        ./Adobe/ directory next to ./Documents/, with the default InDesign
        file named after the project itself —

            ~/Desktop/{project}/Adobe/{project}.indd

        So the Adulting session → Adulting.indd in its own Adobe folder.
        Opening via os.startfile lets Windows route the .indd through
        whichever InDesign install is registered as the default handler;
        we don't care which version, just that one exists.

        If the file isn't there, open the Adobe folder instead so the user
        can drop the file in or see what's present.  Missing Adobe folder
        itself surfaces as an info-bar message rather than an error — this
        is a convenience launcher, not a contract violation.
        """
        import os

        project = self.project_selector.currentText()
        if not project or project == self._NEW_SESSION_SENTINEL:
            self.show_info("No session selected — can't resolve an InDesign file.")
            return

        adobe_dir = Path.home() / "Desktop" / project / "Adobe"
        indd_file = adobe_dir / f"{project}.indd"

        if indd_file.exists():
            try:
                os.startfile(str(indd_file))
                self.show_info(f"Opening {indd_file.name}")
            except OSError as e:
                self.show_info(f"Couldn't open {indd_file.name}: {e}")
            return

        # Fall back: reveal the Adobe folder in Explorer so the user can see
        # what's actually there (and drop in the expected file if missing).
        if adobe_dir.exists():
            try:
                os.startfile(str(adobe_dir))
                self.show_info(f"{indd_file.name} not found — opened the Adobe folder")
            except OSError as e:
                self.show_info(f"Couldn't open Adobe folder: {e}")
        else:
            self.show_info(f"No ./Adobe/ folder in {project} yet")

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
    def _spawn_joy_stats_node(self):
        """
        Summon the singleton JoyStatsNode HUD.

        One JoyStats lives in the entire app. Three cases mirror the
        Companion:
        - already here → pan camera and select
        - parked in limbo (was pinned at last session swap) → re-attach
          at this session's seat
        - never created → spawn fresh and claim as the singleton

        Cross-session persistence is gated by the node's pin state at
        the moment of session swap (see _park_joy_stats). Pinned →
        survives via limbo. Unpinned → dies with its scene.
        """
        from PySide6.QtCore import QPointF

        # Case 1: already in current scene — focus + select
        if self._joy_stats_alive() and self._joy_stats.scene() is self.scene:
            try:
                self.scene.clearSelection()
                self._joy_stats.setSelected(True)
                self.view.centerOn(self._joy_stats)
            except Exception:
                pass
            self._status("the joy stats are right here")
            return

        # Compute landing position — this session's seat or viewport centre
        seat = self._joy_stats_seats.get(self._current_joy_stats_seat_key() or "")
        if seat:
            target = QPointF(seat[0], seat[1])
        else:
            target = self.view.mapToScene(self.view.viewport().rect().center())

        # Case 2: exists in limbo — attach to current scene at the seat
        if self._joy_stats_alive():
            try:
                self.scene.addItem(self._joy_stats)
                r = self._joy_stats.rect()
                self._joy_stats.setPos(target - QPointF(r.width() / 2, r.height() / 2))
                self.scene.raise_node(self._joy_stats)
                self._status("the joy stats are back")
                return
            except Exception:
                self._joy_stats = None  # stale ref, fall through

        # Case 3: first spawn ever
        node = self._spawn(self.scene.add_joy_stats_node, "inspecting the joy bucket")
        if node is None:
            return
        node._is_joy_stats = True
        self._joy_stats = node
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
        _bot_template = "background: {bg};"
        self.bottomToolbar.setStyleSheet(_bot_template.format(bg=Theme.windowBg))
        self._chrome_pulse_targets.append((self.bottomToolbar, _bot_template))

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
        # Font via setFont, NOT QSS font-family — see info_label_top above.
        from pretty_widgets.utils.fonts import chandler42
        self.info_label.setFont(chandler42(size_px=16))
        self.info_label.setStyleSheet(
            f"background: transparent; border: none; padding: 0px 4px 4px 4px;"
            f" color: {Theme.textPrimary};"
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

    # Zoom-slider curve knobs — two cubic Hermite segments meeting at the
    # pivot with shared tangent (C¹ smooth). Tweak to taste. Must stay in
    # lockstep with IntricateView.ZOOM_MIN / ZOOM_MAX — the slider and the
    # view are the same range, expressed at different layers.
    _ZOOM_MIN = 0.01
    _ZOOM_MAX = 5.0
    _ZOOM_PIVOT = 1.0      # zoom value at the pivot
    _PIVOT_T = 0.6         # where the pivot sits on the slider (0..1)
    _PIVOT_SLOPE = 0.4     # zoom per unit slider at the pivot — small = flat
    _END_SLOPE_LOW = 2.5   # zoom per unit slider at slider=0
    _END_SLOPE_HIGH = 12.0 # zoom per unit slider at slider=1

    @classmethod
    def _slider_pos_to_zoom(cls, pos: int) -> float:
        """Map slider position 0-1000 → zoom via two C¹-stitched Hermites."""
        s = max(0.0, min(1.0, pos / 1000.0))
        if s <= cls._PIVOT_T:
            dt = cls._PIVOT_T
            u = s / dt
            y0, y1 = cls._ZOOM_MIN, cls._ZOOM_PIVOT
            m0, m1 = cls._END_SLOPE_LOW * dt, cls._PIVOT_SLOPE * dt
        else:
            dt = 1.0 - cls._PIVOT_T
            u = (s - cls._PIVOT_T) / dt
            y0, y1 = cls._ZOOM_PIVOT, cls._ZOOM_MAX
            m0, m1 = cls._PIVOT_SLOPE * dt, cls._END_SLOPE_HIGH * dt
        u2 = u * u
        u3 = u2 * u
        h00 = 2 * u3 - 3 * u2 + 1
        h10 = u3 - 2 * u2 + u
        h01 = -2 * u3 + 3 * u2
        h11 = u3 - u2
        return h00 * y0 + h10 * m0 + h01 * y1 + h11 * m1

    @classmethod
    def _zoom_to_slider_pos(cls, zoom: float) -> int:
        """Inverse via bisection on the (monotonic) Hermite curve."""
        zoom = max(cls._ZOOM_MIN, min(cls._ZOOM_MAX, zoom))
        if zoom <= cls._ZOOM_PIVOT:
            lo, hi = 0, int(cls._PIVOT_T * 1000)
        else:
            lo, hi = int(cls._PIVOT_T * 1000), 1000
        for _ in range(24):
            mid = (lo + hi) // 2
            if cls._slider_pos_to_zoom(mid) < zoom:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1:
                break
        return lo if abs(cls._slider_pos_to_zoom(lo) - zoom) < abs(cls._slider_pos_to_zoom(hi) - zoom) else hi

    def _on_zoom_slider(self, value: int) -> None:
        """Slider dragged — set the view zoom to the slider's value.

        Guarded against self.view not existing: the sidebar (and hence
        this slider) is now built earlier in __init__ than the view,
        and setting the slider's initial value fires valueChanged once
        during construction. Silently no-op until the view lands.
        """
        if not hasattr(self, 'view'):
            return
        target = self._slider_pos_to_zoom(value)
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
    _MEOV_HOLD_MS    = 30_000       # whisper stays visible 30 s — long enough to notice from across the room

    def _meov_tick(self) -> None:
        """One whispered meov. Escalates by a dot each time the cat waits.
        Occasionally swaps the dots for a single or double exclamation when
        the cat wants to sound a little more insistent than usual.

        First tick also kicks off the titlebar colour-pulse — visual hint
        visible at desk distance even with curtains rolled up.  Idempotent:
        subsequent ticks find the pulse already running and skip.

        Whisper holds 30 s instead of the default 3 s so it doesn't vanish
        before the user looks at the screen — a 3-second meov in the corner
        is too easy to miss; 30 s gives the cat real visible presence."""
        self._meov_level += 1
        if random.random() < self._MEOV_BANG_CHANCE:
            message = "meov" + ("!" * random.randint(1, 2))
        else:
            message = "meov" + ("." * self._meov_level)
        self.show_info(
            message,
            hold_ms=self._MEOV_HOLD_MS,
            on_click=self._acknowledge_meov,
        )
        self._start_meov_color_pulse()
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
        self._stop_meov_color_pulse()

    # ─────────────────────────────────────────────────────────────────────
    # Titlebar meov colour pulse
    # ─────────────────────────────────────────────────────────────────────
    # When the cat is meov-ing the titlebar text fades textPrimary →
    # bright pink → textPrimary on a slow ~3 s loop.  Same #d87a9e endpoint
    # as the canonical 4-stop progress-bar gradient — the family's
    # universal "something is happening" hue.  Visible at desk distance so
    # the user can tell from across the room that Intricate wants
    # attention, even when curtains are rolled and the only signal would
    # otherwise be a small italic glyph at the top of the screen.
    #
    # Pulse runs continuously from the first meov tick until curtains
    # come back down (any tending-to-the-app gesture rolls them).  No
    # amplitude / speed escalation tied to _meov_level — the message
    # itself ("meov...." with growing dot-tail) carries that signal; the
    # colour pulse is the at-distance secondary channel.

    _MEOV_PULSE_DURATION_MS = 3000   # full textPrimary → pink → textPrimary cycle
    _MEOV_PULSE_PEAK        = "#d87a9e"   # bright pink — gradient stop 1.0

    def _titlebar_info_qss(self, color: str) -> str:
        """Build the QSS string for info_label_top with *color* applied.
        Used at construction (textPrimary) and on every pulse tick."""
        return (
            f"background: transparent; border: none; padding: 0px 4px 0px 4px;"
            f" color: {color};"
        )

    def _start_meov_color_pulse(self) -> None:
        """Begin (or no-op continue) the titlebar colour pulse."""
        if not hasattr(self, '_meov_color_anim') or self._meov_color_anim is None:
            from PySide6.QtCore import QVariantAnimation
            from PySide6.QtGui import QColor
            self._meov_color_anim = QVariantAnimation(self)
            self._meov_color_anim.setStartValue(QColor(Theme.textPrimary))
            self._meov_color_anim.setKeyValueAt(0.5, QColor(self._MEOV_PULSE_PEAK))
            self._meov_color_anim.setEndValue(QColor(Theme.textPrimary))
            self._meov_color_anim.setDuration(self._MEOV_PULSE_DURATION_MS)
            self._meov_color_anim.setLoopCount(-1)
            self._meov_color_anim.valueChanged.connect(self._on_meov_color_tick)
        from PySide6.QtCore import QAbstractAnimation
        if self._meov_color_anim.state() != QAbstractAnimation.State.Running:
            self._meov_color_anim.start()

    def _stop_meov_color_pulse(self) -> None:
        """Halt the colour pulse and restore the titlebar's normal hue."""
        if hasattr(self, '_meov_color_anim') and self._meov_color_anim is not None:
            self._meov_color_anim.stop()
        if hasattr(self, 'info_label_top'):
            self.info_label_top.setStyleSheet(self._titlebar_info_qss(Theme.textPrimary))

    def _on_meov_color_tick(self, color) -> None:
        """One frame of the colour pulse — swap just the colour in the QSS."""
        if hasattr(self, 'info_label_top'):
            self.info_label_top.setStyleSheet(self._titlebar_info_qss(color.name()))

    # ─────────────────────────────────────────────────────────────────────
    # Chrome colour pulse (joy-hungry state)
    # ─────────────────────────────────────────────────────────────────────
    # The whole-app surface pulse, distinct from the titlebar-text pulse
    # above.  Fires when joy crosses below the hungry threshold and runs
    # continuously until the user feeds the bar back above.  The chrome
    # surfaces (QMainWindow, top_toolbar, sidebar, bottomToolbar) cycle
    # together so the entire app reads as a calm dark→pink→dark breath
    # — a "she's hungry" signal big enough to register at desk distance
    # without being demanding.  The titlebar text pulse continues to
    # play during whisper messages on top of this background pulse.
    #
    # The user previously had this off for a few weeks.  Brought back
    # 2026-05-03 after the absence proved load-bearing — the cat asking
    # quietly through the whole app's surface is the difference between
    # being noticed and not.

    _CHROME_PULSE_DURATION_MS = 4000   # full dark → pink → dark cycle
    _CHROME_PULSE_PEAK        = "#d87a9e"   # bright pink — gradient stop 1.0

    def _apply_chrome_color(self, color_str: str) -> None:
        """Set *color_str* as the background colour on every registered surface.
        Called per animation tick during the pulse, and on stop with the
        canonical Theme.windowBg to restore the dark base."""
        for widget, template in getattr(self, '_chrome_pulse_targets', ()):
            try:
                widget.setStyleSheet(template.format(bg=color_str))
            except (RuntimeError, AttributeError):
                # Widget torn down or not yet ready — skip silently
                pass

    def _start_chrome_pulse(self) -> None:
        """Begin the joy-hungry chrome pulse — dark base ↔ bright pink, looped."""
        if not hasattr(self, '_chrome_pulse_anim') or self._chrome_pulse_anim is None:
            from PySide6.QtCore import QVariantAnimation
            from PySide6.QtGui import QColor
            self._chrome_pulse_anim = QVariantAnimation(self)
            self._chrome_pulse_anim.setStartValue(QColor(Theme.windowBg))
            self._chrome_pulse_anim.setKeyValueAt(0.5, QColor(self._CHROME_PULSE_PEAK))
            self._chrome_pulse_anim.setEndValue(QColor(Theme.windowBg))
            self._chrome_pulse_anim.setDuration(self._CHROME_PULSE_DURATION_MS)
            self._chrome_pulse_anim.setLoopCount(-1)
            self._chrome_pulse_anim.valueChanged.connect(self._on_chrome_pulse_tick)
        from PySide6.QtCore import QAbstractAnimation
        if self._chrome_pulse_anim.state() != QAbstractAnimation.State.Running:
            self._chrome_pulse_anim.start()

    def _stop_chrome_pulse(self) -> None:
        """Halt the chrome pulse and snap chrome back to the dark base.
        Called on feed (joy_hungry → False)."""
        if hasattr(self, '_chrome_pulse_anim') and self._chrome_pulse_anim is not None:
            self._chrome_pulse_anim.stop()
        self._apply_chrome_color(Theme.windowBg)

    def _on_chrome_pulse_tick(self, color) -> None:
        self._apply_chrome_color(color.name())

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

    def show_info(self, message: str, on_click=None, hold_ms: int = 3000) -> None:
        """Typewriter reveal with simultaneous fade-in, hold *hold_ms*, then fade out.

        Default hold is 3 s — right for save / paste-split / export
        confirmations.  Long-hold messages (meovs, ambient cat presence)
        pass a longer hold_ms so the whisper doesn't vanish before the
        user notices it; visible-for-three-seconds-then-gone is too
        short for an at-distance attention signal.
        """
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
        self._active_hold_ms = max(0, int(hold_ms))
        self._active_label.setText("")
        self._active_label.setCursor(
            Qt.PointingHandCursor if on_click else Qt.ArrowCursor
        )

        # Fade in over the expected typing duration so opacity climbs with the text
        fade_ms = max(400, len(message) * 55)
        self._animate_info_opacity(0.0, 1.0, fade_ms)

        # If the active label is the titlebar mirror, take it out of
        # mouse-passthrough mode so clicks land on the message rather
        # than passing through to the QMainWindow drag handler.  Set
        # AFTER _animate_info_opacity since that path may stop a previous
        # fade-out animation whose `finished` slot would also touch this
        # attribute — running the set here ensures the post-stop state
        # ends up correct regardless of late-firing slot order.
        if self._active_label is self.info_label_top:
            self._set_info_label_top_passthrough(False, reason="show_info active")

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
            self._info_timer.start(getattr(self, '_active_hold_ms', 3000))

    def _fade_info_out(self) -> None:
        # Stop the hold timer so it can't fire a second _fade_info_out after
        # a manual click-dismissal.  Without this, a click that fades the
        # message early would later get followed by the timer firing the
        # same method, which restarts the fade animation from opacity 1 →
        # producing a visible flash of the already-dismissed message.
        # Calling stop() on a stopped timer is a safe no-op so the
        # timer-driven path stays unchanged.
        if hasattr(self, '_info_timer'):
            self._info_timer.stop()
        self._info_click_action = None
        target = getattr(self, '_active_label', self.info_label)
        target.setCursor(Qt.ArrowCursor)
        self._animate_info_opacity(1.0, 0.0, 600)

    def _acknowledge_meov(self) -> None:
        """Click handler for the meov whisper — the gentle ear-scratch.

        Dismisses the visible whisper but leaves the chrome pulse and
        meov timer untouched, since the cat is still hungry — this is
        the user saying "I see you, I'm on it," not actually feeding her.
        Same as a real cat: the scratch quiets her current ask without
        resetting the underlying need.
        """
        self._fade_info_out()

    def _animate_info_opacity(self, start: float, end: float, duration: int) -> None:
        if self._info_anim:
            # Was the previous animation a fade-OUT?  If so, its `finished`
            # slot was supposed to restore titlebar drag passthrough — but
            # we're about to stop it before completion.  Capture the
            # direction now so we can run the restore manually below.
            try:
                prev_was_fade_out = float(self._info_anim.endValue()) <= 0.01
            except (TypeError, AttributeError):
                prev_was_fade_out = False
            # Disconnect any previous `finished` handlers BEFORE stop().
            # Without the disconnect, a previous fade-out's queued slot
            # would fire right now and toggle info_label_top's passthrough
            # back on in the middle of starting a new fade-in.  Two
            # disconnect() forms covered: no-arg (all slots) and
            # TypeError fallback for the case where there were no
            # connections to begin with.
            try:
                self._info_anim.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._info_anim.stop()
            # The disconnected fade-out won't fire its finished slot
            # anymore.  Run the passthrough restore manually so we don't
            # leave info_label_top stuck blocking mouse events when no
            # message is actually visible.  Idempotent via the helper's
            # no-op branch, so calling it on an already-passthrough state
            # is a logged no-op.
            if prev_was_fade_out:
                self._set_info_label_top_passthrough(
                    True, reason="stop() interrupted fade-out — manual cleanup"
                )
        effect = getattr(self, '_active_opacity', self._info_opacity)
        self._info_anim = QPropertyAnimation(effect, b"opacity")
        self._info_anim.setDuration(duration)
        self._info_anim.setStartValue(start)
        self._info_anim.setEndValue(end)
        # Fade-OUT animations restore the titlebar drag passthrough on
        # info_label_top once the fade completes.  Fade-IN animations
        # don't connect finished — passthrough was set to False by
        # show_info before this method ran.
        if end <= 0.01:
            self._info_anim.finished.connect(self._on_info_fade_out_done)
        self._info_anim.start()

    def _on_info_fade_out_done(self) -> None:
        """Restore titlebar drag passthrough once the message has fully
        faded.  Called from the fade-out animation's `finished` signal,
        not from external callers.  Idempotent — calling when already in
        passthrough state is a logged no-op via the `_set_*` helper."""
        self._set_info_label_top_passthrough(True, reason="fade-out complete")

    def _set_info_label_top_passthrough(self, passthrough: bool, *, reason: str = "") -> None:
        """Toggle WA_TransparentForMouseEvents on info_label_top.

        ``passthrough=True``  → label is invisible to mouse events; clicks
        fall through to the QMainWindow titlebar drag handler.  Used when
        no message is visible.

        ``passthrough=False`` → label receives mouse events normally; the
        on_click handler fires when clicked.  Used during the visible
        portion of a message lifecycle (typewriter, hold, fade-out).

        Logs every transition with the reason so the toggling can be
        diagnosed if the behaviour ever feels wrong — overlapping hit
        regions in Qt are notoriously tricky to debug without a trail.
        Wrapped in try/except since the label can be torn down by
        parent destruction in some edge paths.
        """
        if not hasattr(self, 'info_label_top'):
            return
        try:
            current = self.info_label_top.testAttribute(Qt.WA_TransparentForMouseEvents)
            if current == passthrough:
                logger.debug(
                    "[infobar-passthrough] no-op (%s, reason=%s)",
                    "passthrough" if passthrough else "blocking",
                    reason or "(unspecified)",
                )
                return
            self.info_label_top.setAttribute(Qt.WA_TransparentForMouseEvents, passthrough)
            logger.debug(
                "[infobar-passthrough] %s → %s — drag %s (reason=%s)",
                "passthrough" if current else "blocking",
                "passthrough" if passthrough else "blocking",
                "passes through" if passthrough else "blocked by visible message",
                reason or "(unspecified)",
            )
        except RuntimeError:
            # info_label_top torn down by parent destruction — silently OK
            pass

    def _sync_zoom_slider(self) -> None:
        """Called after wheel-zoom to keep the slider in sync with the view."""
        pos = self._zoom_to_slider_pos(self.view.current_zoom)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(pos)
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
            # newline="\n" keeps the file LF on Windows; without it write_text
            # routes through text-mode translation and produces CRLF endings
            # that conflict with .gitattributes eol=lf.
            p.write_text(json.dumps(self._companion_seats, indent=2),
                         encoding="utf-8", newline="\n")
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

    # ── JoyStats — app-scoped singleton, pin-gated cross-session travel ─────
    #
    # Mirrors the Companion lifecycle but with one twist: only PINNED
    # JoyStats nodes traverse session swaps. An unpinned JoyStats lives in
    # the current session's saved data like any other node and dies with
    # the scene on swap. A pinned JoyStats is excluded from session save,
    # parked in a persistent limbo scene during the swap, and reattached at
    # this session's remembered seat.

    def _joy_stats_alive(self) -> bool:
        """True if self._joy_stats holds a living QGraphicsItem."""
        if self._joy_stats is None:
            return False
        try:
            self._joy_stats.scene()  # raises RuntimeError if C++ side gone
            return True
        except RuntimeError:
            self._joy_stats = None
            return False

    def _joy_stats_sidecar_path(self):
        """Fixed app-global path for the JoyStats seat map."""
        from pathlib import Path as _P
        return _P(__file__).resolve().parent / "Documents" / "Data" / "joy_stats.json"

    def _load_joy_stats_seats(self) -> dict:
        """Load session_key → (x, y) seat map, or {} if absent."""
        import json
        p = self._joy_stats_sidecar_path()
        if not p.exists():
            return {}
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return {str(k): list(v) for k, v in raw.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2}
        except Exception:
            logger.exception("[joy-stats] failed to load seats sidecar")
            return {}

    def _save_joy_stats_seats(self) -> None:
        """Persist the seat map. Non-fatal on failure."""
        import json
        try:
            p = self._joy_stats_sidecar_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n" — same reason as _save_companion_seats: prevent
            # Windows CRLF translation conflicting with eol=lf attribute.
            p.write_text(json.dumps(self._joy_stats_seats, indent=2),
                         encoding="utf-8", newline="\n")
        except Exception:
            logger.exception("[joy-stats] failed to save seats sidecar")

    def _current_joy_stats_seat_key(self) -> str | None:
        try:
            path = self._session_path()
        except Exception:
            return None
        return str(path) if path else None

    def _park_joy_stats(self) -> None:
        """
        Pre-swap park. PINNED → record seat, transfer to limbo so it
        survives the scene swap. UNPINNED → leave it in the outgoing
        scene to be saved/destroyed normally and clear the singleton ref.
        """
        if not self._joy_stats_alive():
            return
        if self._joy_stats.scene() is not self.scene:
            return  # already parked

        key = self._current_joy_stats_seat_key()
        if key:
            try:
                p = self._joy_stats.scenePos()
                self._joy_stats_seats[key] = [p.x(), p.y()]
            except Exception:
                pass

        pinned = bool(getattr(self._joy_stats.data, 'pinned', False))
        if not pinned:
            # Unpinned — let it ride the outgoing scene out. It'll be saved
            # to session.json by the normal save path and torn down with the
            # scene on _swap_scene. The singleton ref is cleared so the next
            # session's spawn / load path can claim a fresh one.
            self._joy_stats = None
            return

        # Set _pinned_across_scenes transiently around the cross-scene move:
        # Qt's addItem internally does removeItem-then-addItem, briefly firing
        # ItemSceneChange with value=None. Both BaseNode and ChromelessRoot
        # would otherwise interpret that as a destruction signal and run the
        # demolition crew — which severs viewport-tracking signals, breaking
        # the pin after re-attach. Scoped to the transfer so shake-delete and
        # other genuine scene-leave paths still demolish normally.
        try:
            self._joy_stats._pinned_across_scenes = True
            self._joy_stats_limbo.addItem(self._joy_stats)
        except Exception:
            logger.exception("[joy-stats] transfer to limbo failed")
            self._joy_stats = None
        finally:
            try:
                if self._joy_stats is not None:
                    self._joy_stats._pinned_across_scenes = False
            except Exception:
                pass

    def _attach_joy_stats(self) -> None:
        """
        Post-load attach. If we're holding a pinned singleton in limbo,
        place it in the new scene and drop any duplicate that came in via
        session load. If we're not, capture any session-loaded JoyStats
        as the new singleton.
        """
        from nodes.JoyStatsNode import JoyStatsNode
        from PySide6.QtCore import QPointF

        if self._joy_stats_alive():
            # Drop any duplicate that arrived through session load — our
            # limbo instance is canonical.
            for item in list(self.scene.items()):
                if (isinstance(item, JoyStatsNode)
                        and item is not self._joy_stats):
                    try:
                        self.scene.removeItem(item)
                    except Exception:
                        pass
            if self._joy_stats.scene() is self.scene:
                return  # already there
            key = self._current_joy_stats_seat_key()
            seat = self._joy_stats_seats.get(key or "") if key else None
            if seat:
                target = QPointF(seat[0], seat[1])
            else:
                target = self.view.mapToScene(self.view.viewport().rect().center())
            try:
                # Same transient guard as in _park_joy_stats — suppresses
                # demolition during the cross-scene addItem race.
                self._joy_stats._pinned_across_scenes = True
                self.scene.addItem(self._joy_stats)
                r = self._joy_stats.rect()
                self._joy_stats.setPos(target - QPointF(r.width() / 2, r.height() / 2))
                self.scene.raise_node(self._joy_stats)
            except Exception:
                logger.exception("[joy-stats] attach failed — ref cleared")
                self._joy_stats = None
            finally:
                try:
                    if self._joy_stats is not None:
                        self._joy_stats._pinned_across_scenes = False
                except Exception:
                    pass
            # Re-arm viewport tracking if the node is pinned. _connect has
            # an "already connected, skip" guard so this is a no-op when
            # tracking survived the round-trip; when it didn't (legacy
            # break, demolition fired before the flag was honoured), this
            # reattaches signals to the live view and snaps the node back
            # to its saved pin_vp.
            try:
                if (self._joy_stats is not None
                        and getattr(self._joy_stats.data, 'pinned', False)):
                    self._joy_stats._activate_pin(from_saved_vp=True)
            except Exception:
                logger.exception("[joy-stats] pin re-arm failed")
            return

        # No singleton held — capture the first JoyStats from the loaded
        # session (if any) and stamp it as the singleton.
        for item in self.scene.items():
            if isinstance(item, JoyStatsNode):
                self._joy_stats = item
                item._is_joy_stats = True
                break

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
            from shared_braincell.logger import setup_logger
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
        # Claim any session-saved JoyStats as the app-scoped singleton so
        # the spawn button focuses it instead of creating a duplicate.
        self._attach_joy_stats()
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
        self._park_joy_stats()

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
        self._attach_joy_stats()
        self._status(f"welcome back to {new_project}")

    # ─────────────────────────────────────────────────────────────────────
    # Dialog-choreography mixin context. IntricateApp IS the main window,
    # so the default scene-traversing lookup doesn't apply — return self.
    # See nodes/_dialog_helper.py for the framework.
    # ─────────────────────────────────────────────────────────────────────

    def _get_main_window(self):
        return self

    def _create_new_session(self) -> None:
        """Prompt for a name, create the folder, and switch to the new session."""
        prev = getattr(self, '_active_project', '')

        # Curtain dance, HWND settle, focus, and restore — all handled
        # by the choreography mixin (matches GitNode's commit-dialog
        # pattern). _PrettyDialogBase.showEvent then centres the dialog
        # and asserts topmost-band dominance.
        with self._dialog_choreography() as mw:
            dlg = _NewSessionDialog(parent=mw)
            result = dlg.exec()

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
        self._park_joy_stats()

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
        self._attach_joy_stats()
        self._status(f"welcome to {name}")

    def _git_init_project(self, project_dir: Path, name: str) -> None:
        """git init + .gitignore + README + initial commit for a new project folder."""
        import subprocess as _sp
        try:
            _run = lambda cmd: _sp.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True, timeout=15
            )
            _run(["git", "init"])
            # newline="\n" on both — these land in a fresh git repo and LF
            # is the portable choice for .gitignore + README.md.
            gitignore = project_dir / ".gitignore"
            gitignore.write_text(
                "__pycache__/\n*.pyc\n.env\n*.log\nlogs/\n",
                encoding="utf-8",
                newline="\n",
            )
            readme = project_dir / "README.md"
            readme.write_text(
                f"# {name}\n\nIt is what it is\n",
                encoding="utf-8",
                newline="\n",
            )
            _run(["git", "add", "."])
            _run(["git", "commit", "-m", f"init {name}"])
            logger.info(f"[session] git init complete for {name}")
        except Exception:
            logger.warning(f"[session] git init failed for {name}", exc_info=True)

    _NEW_SESSION_SENTINEL = "+ New Session"

    @staticmethod
    def _project_sort_key(name: str) -> str:
        """Sort 'The Foo' as if it were 'Foo' — honours the 'The …' naming
        habit without piling everything into the T of the alphabet. Falls
        through to the actual name when there's no 'The ' prefix. Casefold
        keeps mixed casing from jumbling order across OS filesystems."""
        stripped = name[4:] if name[:4].lower() == "the " else name
        return stripped.casefold()

    def populate_sessions(self) -> None:
        desktop = Path.home() / "Desktop"
        desktop_folders = sorted(
            (p.name for p in desktop.iterdir()
             if p.is_dir() and not p.name.startswith(".")
             and p.name != self._NEW_SESSION_SENTINEL
             and p.name != "_runtime"),
            key=self._project_sort_key,
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
        logger.info(pick_phrase())
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
            # Same dance for the JoyStats HUD — record final seat (if it's
            # currently on canvas) before scene teardown, then flush sidecar.
            try:
                if (self._joy_stats_alive()
                        and self._joy_stats.scene() is self.scene):
                    key = self._current_joy_stats_seat_key()
                    if key:
                        p = self._joy_stats.scenePos()
                        self._joy_stats_seats[key] = [p.x(), p.y()]
                self._save_joy_stats_seats()
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
        # Joy state save-on-close. Without this, the most recent persist was
        # up to 30 seconds ago (during the depletion tick) — and with the
        # restart-on-close spawn pattern, the next instance reads the file
        # before the old instance ever writes again. Calling _persist_happy
        # explicitly here stamps the bar value AND last_active_at at the
        # actual moment of close, which feeds the wake-decay calculation
        # on the next launch (see _apply_sleep_decay_on_wake below).
        try:
            self._persist_happy()
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
