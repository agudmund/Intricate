#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/BaseNode.py BaseNode class
-The visual and structural foundation every node type builds on, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time as _time
import uuid as _uuid
from contextlib import contextmanager
from PySide6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QApplication
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer, QVariantAnimation, QEasingCurve, QEventLoop, QAbstractAnimation
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QFont
from PySide6.QtWidgets import QGraphicsItem
from shared_braincell.logger import setup_logger

logger = setup_logger("basenode")

from data.NodeData import NodeData
from nodes.NodeBehaviour import NodeBehaviour
from pretty_widgets.graphics.Theme import Theme
from nodes.NodeButton import NodeButton, EmojiButton, BUTTON_SIZE
from nodes._shake_detect import arm_cooldown as _arm_shake_cooldown, is_cooling_down as _shake_cooling_down


def _c(hex_str): return QColor(hex_str)   # local shorthand


# Visual constants resolved from Theme at import time
_BG              = _c(Theme.nodeBg)
_BORDER          = _c(Theme.nodeBorder)
_BORDER_SELECTED = _c(Theme.nodeBorderSelected)
_BORDER_WIDTH    = Theme.nodeBorderWidth
_BORDER_SELECTED_SCALE = Theme.nodeBorderSelectedScale
_ROUND_RADIUS    = Theme.nodeRoundRadius
_SHADOW_MARGIN   = Theme.nodeShadowMargin
_MIN_WIDTH       = Theme.nodeMinWidth
_MIN_HEIGHT      = Theme.nodeMinHeight
_RESIZE_GRIP     = Theme.nodeResizeGrip
# How far the resize hit zone extends past the bottom-right corner so the
# grip is still catchable when the cursor lands a few pixels outside the
# visible border (the common miss case for nearly-on-edge grabs).
_RESIZE_OVERREACH = 6


class BaseNode(QGraphicsRectItem):
    """
    The stage every node type performs on.

    BaseNode owns everything structural and visual that is universal across
    all node types: ports, connections, resize, hover pulse, shadow, paint
    pipeline, and the session lifecycle contract.

    What BaseNode does NOT own:
        - Node data (lives in NodeData, passed in at construction)
        - Node personality (lives in NodeBehaviour, attached at construction)
        - Type-specific visuals (paint_content() — override in subclasses)
        - Type-specific serialization (to_dict()/from_dict() — extend in subclasses)

    Subclassing contract:
        paint_content(painter)     — draw type-specific content inside the node body.
        mouseDoubleClickEvent(e)   — override for type-specific double-click behaviour.
        to_dict() / from_dict()    — extend NodeData subclass, not BaseNode.

    Lifecycle contract:
        _prepare_for_removal() fires deterministically when the node leaves
        its scene via itemChange. It stops animations, severs wire connections,
        and disconnects Qt signals so Python's GC can collect cleanly.

        Sessions are independent. No node reference survives a session switch.
    """

    # Subclasses can enlarge the resize grip by overriding this class attr.
    # Default tracks the theme value; VideoNode etc. set their own.
    _resize_grip = _RESIZE_GRIP
    # How far past the bottom-right corner the resize hit zone extends.
    # Default 6 — catches nearly-on-edge grabs. Subclasses with a roomy
    # grip and a child item near the corner (e.g. VideoNode's BR port)
    # can drop this to 0 to keep the resize zone strictly inside the rect.
    _resize_overreach = _RESIZE_OVERREACH

    def __init__(self, data: NodeData):
        """
        Construct a BaseNode from a NodeData instance.

        Args:
            data: The identity, geometry, and state of this node.
                  BaseNode reads from data to set its initial visual state.
                  Data is stored on self.data — subclasses access it there.
        """
        super().__init__(0, 0, data.width, data.height)

        # ── Data ──────────────────────────────────────────────────────────────
        # The node's identity and state. Qt reads from here, never writes here.
        # Assign a random accent emoji if none was persisted from a prior session.
        if not data.emoji or data.emoji == "🌿":
            from utils.pickers.IconPicker import randomling as pick_emoji
            data.emoji = pick_emoji()
        self.data = data
        self.setPos(QPointF(data.x, data.y))

        # ── Connections ───────────────────────────────────────────────────────
        self.connections = []           # All Connection objects attached to this node
        self.temp_connection = None     # Active wire being drawn, cleared on release
        self.ports_visible = data.ports_visible

        # ── Ports ─────────────────────────────────────────────────────────────
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.input_ports  = []          # 4 corner input ports (TL, TR, BL, BR)
        self.output_ports = []          # 4 corner output ports (TL, TR, BL, BR)
        self.input_port   = None        # kept for backwards-compat — alias to TL
        self.output_port  = None        # kept for backwards-compat — alias to TL
        self._create_ports()

        # ── Resize state ──────────────────────────────────────────────────────
        self._is_resizing      = False
        self._resize_start_pos  = QPointF()
        self._resize_start_rect = QRectF()
        self._min_width         = _MIN_WIDTH
        self._min_height        = _MIN_HEIGHT

        # ── Position throttle ─────────────────────────────────────────────────
        # Connection redraws are batched so rapid movement doesn't flood the scene.
        self._update_throttle_timer = None
        self._pending_update        = False
        self._last_scene_pos        = QPointF(data.x, data.y)

        # ── Shake-to-detach / shake-to-delete ────────────────────────────────
        self._shake_samples: list       = []    # [(monotonic_time, QPointF), ...]
        self._shake_triggered: bool     = False
        self._shake_press_active: bool  = False
        self._pending_shake_delete: bool = False
        self._removal_done: bool = False

        # ── Drag-commit dead zone — Wacom phantom-motion guard ───────────────
        # Stationary Wacom-pen taps generate a stream of synthesized mouse-
        # move events as Windows transitions the OS cursor to the pen contact
        # point. Without this gate, default ItemIsMovable translates the node
        # along the synthesized path and the shake detector samples that path
        # — manifesting as "node propelled offscreen on touch" or
        # "node deleted on touch". Diagnosis closed 2026-04-29 from forensic
        # logs at 14:59:39 (ChromelessRoot family); same fix applied here.
        # See ChromelessRoot._DRAG_COMMIT_THRESHOLD_PX for the rationale.
        self._drag_press_screen_pos = QPointF()
        self._drag_committed        = False
        self._drag_suppressed_count = 0
        self._drag_suppressed_max_travel_px = 0.0

        # ──────────────────────────────────────────────────────────────────────
        # Press/release balance counters — diagnostic for the 2026-05-02
        # "click sends node spinning far offscreen" bug class.
        #
        # The original symptom: a gentle click on a node sometimes sent it
        # spinning far offscreen, identified as a series of up to 35 click
        # events firing in rapid succession. The first investigation traced
        # one mechanism: mousePressEvent's resize-handle early-return path
        # was calling event.accept() and returning WITHOUT calling
        # super().mousePressEvent(). Meanwhile, mouseReleaseEvent always
        # called super().mouseReleaseEvent() — meaning the press half of
        # the gesture skipped Qt's internal anchor setup, but the release
        # half ran against whatever stale anchor was last cached (possibly
        # from a press minutes ago, on a different node). Qt then computed
        # a translation delta against the stale anchor and snapped the
        # item by that delta. With a multi-minute stale anchor, the delta
        # is huge — node spins offscreen.
        #
        # The fix paired with this counter: super().mousePressEvent() is
        # now called on EVERY press path (resize-handle path included) so
        # the press/release halves stay symmetric from Qt's view. The
        # counters below let us detect imbalance if a different mechanism
        # ever surfaces — _arm_seq increments on every mousePressEvent
        # (any button, any path), _release_seq on every mouseReleaseEvent.
        # Steady state has _release_seq one behind _arm_seq during a
        # gesture and equal between gestures. A release that fires while
        # _release_seq == _arm_seq is an "orphan release" — Qt sent us a
        # release without a corresponding press through this method, and
        # gets logged at WARNING for forensic capture. The orphan handler
        # re-syncs _release_seq = _arm_seq after warning so a single
        # asymmetric gesture (e.g. mouseDoubleClickEvent dispatch) fires
        # exactly one WARNING instead of latching into a cascade where
        # every subsequent legitimate release reads as orphan.
        self._arm_seq:     int = 0
        self._release_seq: int = 0

        # Outstanding-press flag — gates mouseMoveEvent against asymmetric
        # Qt event dispatch. Set True on every mousePressEvent entry,
        # False on every mouseReleaseEvent exit. Used by mouseMoveEvent
        # instead of an _arm_seq <= _release_seq comparison: the seq-based
        # gate latched permanently after the first orphan release because
        # the seqs drifted by 1 forever, leaving the node unmovable.
        # A boolean is binary — it cannot drift and cannot latch.
        self._press_outstanding: bool = False

        # ── Behaviour ─────────────────────────────────────────────────────────
        # disconnect_all() is called in _prepare_for_removal — not optional.
        self.behaviour = NodeBehaviour(self)

        # ── Visuals ───────────────────────────────────────────────────────────
        _bw  = Theme.nodeBorderWidth
        _bc  = QColor(Theme.nodeBorder)
        _bcs = QColor(Theme.nodeBorderSelected)
        _bss = Theme.nodeBorderSelectedScale
        self.round_radius  = Theme.nodeRoundRadius
        self.normal_pen    = QPen(_bc, _bw)
        self.hover_pen     = QPen(QColor(Theme.nodeBorderHover), _bw)
        self.selected_pen  = QPen(_bcs, _bw * _bss)
        self.current_pen   = self.normal_pen

        self.setBrush(QColor(Theme.nodeBg))
        self.setPen(self.current_pen)

        # ── Node tint ─────────────────────────────────────────────────────────
        # -1 = no tint (natural color); 0..N = index into ColorPicker palette.
        # _untinted_brush is captured lazily on first button press so subclass
        # setBrush calls that run after super().__init__() are always captured.
        self._color_index    = -1
        self._untinted_brush = None
        _saved_tint = getattr(self.data, 'node_tint', '')
        if _saved_tint:
            # register() is idempotent: seed colors resolve to their existing
            # index, custom colors get appended so the toggle button can
            # rotate back to them instead of silently snapping to palette[0].
            from utils.pickers.ColorPicker import register as _register
            self._color_index = _register(_saved_tint)

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable      |
            QGraphicsRectItem.ItemIsSelectable   |
            QGraphicsRectItem.ItemSendsGeometryChanges |
            QGraphicsRectItem.ItemSendsScenePositionChanges
        )
        self.setAcceptHoverEvents(True)
        self.setFiltersChildEvents(True)   # route right-clicks through sceneEventFilter
        self.setTransformOriginPoint(self.rect().center())

        # Cache the rendered node in device space — during pan the cached pixmap
        # is reused instead of repainting every node on every frame.
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)


        # ── Collapsible button shelf state ───────────────────────────────────
        # Initialised before buttons so layout methods can reference _anim_top_offset.
        # Restored from data.shelf_visible so the toggle survives session save/load.
        # Subclasses can still override _buttons_visible after super().__init__
        # to force a collapsed default (e.g. AboutNode).
        self._buttons_visible = getattr(self.data, 'shelf_visible', True)
        self._anim_top_offset = self._BUTTON_ZONE_H if self._buttons_visible else self._HIDDEN_TOP_OFFSET

        # ── Button strip ──────────────────────────────────────────────────────
        # Built last — geometry must be final before positioning.
        # Subclasses append their own buttons by overriding _build_buttons().
        self._buttons: list[NodeButton] = []
        self._build_buttons()
        self._position_buttons()
        if not self._buttons_visible:
            for btn in self._buttons:
                btn.hide()

        # ── Shelf animation ──────────────────────────────────────────────────
        self._shelf_anim = QVariantAnimation()
        self._shelf_anim.setDuration(250)
        self._shelf_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._shelf_anim.valueChanged.connect(self._on_shelf_tick)
        self._shelf_anim.finished.connect(self._on_shelf_done)

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def sceneEventFilter(self, watched, event) -> bool:
        """Intercept right-clicks on child items (QGraphicsProxyWidgets, etc.)
        before they reach the child, so BaseNode can start a connection wire
        instead of the child eating the click for its own context menu.

        Exception: a *visible* QGraphicsProxyWidget means the user is actively
        editing.  Subclasses override ``_show_proxy_context_menu(event)`` to
        show their edit-context menu directly at press time — we can't rely
        on Qt's QContextMenuEvent dispatch here because View.mousePressEvent
        calls setFocus() on itself on every press, which defocuses the
        editor → commit_on_focus_loss → proxy.hide() before the follow-up
        QContextMenuEvent can reach the embedded widget."""
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QGraphicsProxyWidget
        if (event.type() == QEvent.GraphicsSceneMousePress
                and event.button() == Qt.RightButton):
            # Visible proxy = active editor.  Let the press reach the
            # inner QWidget's mousePressEvent — the widget handles its
            # own right-click menu there (see _SmartPrettyEdit).  If we
            # intercepted here we'd also kill the release + context-menu
            # dispatch Qt would otherwise send to the child.
            if isinstance(watched, QGraphicsProxyWidget) and watched.isVisible():
                return False
            self.mousePressEvent(event)
            return True   # handled — child does not see it
        return super().sceneEventFilter(watched, event)

    def itemChange(self, change, value):
        # ── Scene-change demolition trigger ──────────────────────────────────
        #
        # This is the load-bearing hook that guarantees every node leaving a
        # scene gets its demolition crew phase — disconnects, timer stops,
        # proxy teardown, behaviour disconnect_all. Without it, signal
        # connections on inner QWidgets outlive their Python host and crash
        # the C++ side (see Documents/Compliance/Node Cleanup Compliance.md,
        # "ClaudeNode inner-widget signal-destructor race" — 0xc0000409 /
        # STATUS_STACK_BUFFER_OVERRUN, 2026-04-18). This hook must stay
        # aggressive. Do not weaken its conditions.
        #
        # The `_pinned_across_scenes` opt-out exists for exactly ONE case:
        # the app-scoped Companion (main_window.py _park_companion), which
        # transfers between a live session scene and a limbo holder scene
        # so it can follow the user across session switches. Qt's cross-
        # scene move is not atomic — it fires this event with value=None
        # mid-flight (internally remove-then-add), which without the pin
        # would tear the companion down between scenes.
        #
        # ⚠  Before adding any other node type to the pin list:
        #     1. Confirm the node genuinely survives across scenes — it
        #        holds identity beyond a single session (e.g. a HUD node
        #        that belongs to the app, not the canvas).
        #     2. Confirm it has a legitimate home during the transition —
        #        a persistent limbo scene on the app, not scene()==None.
        #        A pinned node whose scene is never set again will never
        #        demolish and will leak on app shutdown.
        #     3. Understand the failure mode: if you pin a node that
        #        should have been demolished, its inner-widget signal
        #        connections outlive the C++ widget and the app crashes
        #        on the NEXT unrelated thing that touches those widgets.
        #        The crash will look nothing like "I pinned something";
        #        it will look like a random Qt fastfail in ucrtbase.dll.
        #     4. Add the new node type to the list below, so future
        #        greppers find every pinned node from one place.
        #
        # Currently pinned: ClaudeNode (the Companion, one per app).
        if (change == QGraphicsRectItem.GraphicsItemChange.ItemSceneChange
                and value is None and not self._removal_done
                and not getattr(self, '_pinned_across_scenes', False)):
            logger.log(5, "[REMOVE] %s %s leaving scene — _prepare_for_removal starting",
                        self.data.node_type, self.data.uuid[:8])
            self._prepare_for_removal()
            logger.log(5, "[REMOVE] %s %s _prepare_for_removal complete",
                        self.data.node_type, self.data.uuid[:8])

        if change == QGraphicsRectItem.GraphicsItemChange.ItemSelectedHasChanged:
            if hasattr(self, 'behaviour') and self.behaviour:
                self.behaviour.on_selected(bool(value))
            for conn in self.connections:
                conn.update()

        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            new_pos = self.scenePos()
            if self._last_scene_pos is not None:
                dx = abs(new_pos.x() - self._last_scene_pos.x())
                dy = abs(new_pos.y() - self._last_scene_pos.y())
                if dx < 0.5 and dy < 0.5:
                    return super().itemChange(change, value)
            self._last_scene_pos = new_pos
            self._pending_update = True
            if not self._update_throttle_timer:
                self._update_throttle_timer = QTimer()
                self._update_throttle_timer.setSingleShot(True)
                self._update_throttle_timer.timeout.connect(self._flush_connection_update)
                self._update_throttle_timer.start(16)   # ~1 frame

        return super().itemChange(change, value)

    def _heal_connections(self):
        """
        When this node is deleted, bridge its input sources directly to its
        output targets so the chain is not broken.

        A → self → B  becomes  A → B.
        Multiple sources / targets produce a full cross-join.
        Only fires when both sides have at least one live node.
        """
        scene = self.scene()
        if not scene:
            return
        try:
            sources = [c.start_node for c in self.connections
                       if c.end_node is self and c.start_node is not None]
            targets = [c.end_node   for c in self.connections
                       if c.start_node is self and c.end_node is not None]
        except RuntimeError:
            return
        if not sources or not targets:
            return
        from graphics.Connection import Connection
        for src in sources:
            for tgt in targets:
                if src is tgt:
                    continue
                try:
                    new_conn = Connection(src, tgt)
                    scene.addItem(new_conn)
                    new_conn.update_path()
                except Exception:
                    pass

    # ── Demolition manifest ──────────────────────────────────────────────
    # Universal items every BaseNode carries: the shelf animation that
    # drives button-strip expand/collapse, and the throttle timer that
    # batches connection repaints after ItemPositionChange bursts.
    # Subclasses extend these with their own declarations.
    _demolition_animations = [
        ('_shelf_anim', ['valueChanged', 'finished']),
    ]
    _demolition_timers = [
        ('_update_throttle_timer', '_flush_connection_update'),
    ]

    def _timer_slot_alive(self, timer_attr: str = None) -> bool:
        """Liveness probe for QTimer slots that outlive their C++ owner.

        Orphan ``QTimer()`` instances (timers created without a QObject
        parent — standard pattern across dashboard nodes because
        QGraphicsRectItem isn't a QObject) can fire after the node's
        C++ side has been destroyed on non-deterministic shutdown paths
        (scene scrapped wholesale without routing items through
        ``itemChange → _prepare_for_removal``).  Any Qt-method access on
        a dead wrapper raises ``RuntimeError`` from libshiboken, which
        propagates through Qt's C++ event loop and manifests as a
        STATUS_STACK_BUFFER_OVERRUN (0xC0000409) in ucrtbase.dll.

        Call this at the top of every timer-slot method that touches
        Qt state::

            def _poll_gc(self):
                if not self._timer_slot_alive('_poll_timer'):
                    return
                ...

        When *timer_attr* is given and the wrapper is dead, the named
        timer is stopped + disconnected so it can't fire again.  Pass
        ``None`` for slots that don't own their timer (shared timers
        live elsewhere).  Returns ``True`` when it's safe to proceed.
        """
        try:
            _ = self.scene
            self.scene()
        except RuntimeError:
            if timer_attr:
                t = getattr(self, timer_attr, None)
                if t is not None:
                    try:
                        t.stop()
                        t.timeout.disconnect()
                    except (RuntimeError, TypeError, AttributeError):
                        pass
            return False
        return True

    def _prepare_for_removal(self):
        """
        Graceful exit — called when the node is leaving its scene.

        Delegates to the demolition crew in `nodes/_demolition.py`.  The
        crew handles the standard 5-phase sequence (flush / heal /
        detach / behaviour / sever), walks the node's declarative
        manifest (proxies, timers, animations, threads, media, workers),
        and invokes optional `_demolition_pre` / `_demolition_post`
        hooks for bespoke work.  A node's entire teardown logic can now
        live in class-level manifest attributes — no override needed
        unless the node has truly bespoke ordering requirements.
        """
        from nodes._demolition import demolish
        demolish(self)

    def _flush_connection_update(self):
        """Flush batched connection redraws after the throttle period."""
        self._update_throttle_timer = None
        if not self.scene():
            self._pending_update = False
            return
        if self._pending_update:
            for conn in self.connections:
                conn.update_path()
            # Repaint only the wires whose bounding rect overlaps this node —
            # they may need to update their opacity fade as this node moved under them.
            own      = set(self.connections)
            node_rect = self.mapRectToScene(self.boundingRect())
            for item in self.scene().items(node_rect):
                if hasattr(item, 'start_node') and item not in own:
                    item.update()
            self._pending_update = False

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTON STRIP
    # ─────────────────────────────────────────────────────────────────────────

    _has_depth_toggle = False   # set to True in subclasses that want the front/back button
    _show_ports_btn   = False   # DEBUG ONLY — shows port visibility toggle button.
                                # Ports drive wire connection curves. This button is for
                                # debug inspection of connection geometry, not for end users.
                                # Leave False unless actively debugging wire routing.
    _show_emoji_btn   = True    # set to False in subclasses that skip the emoji shuffler

    def _build_buttons(self) -> None:
        """
        Construct the button strip. Base adds the universal delete button,
        and optionally a ports toggle (_show_ports_btn) or depth toggle
        (_has_depth_toggle) if the respective class flag is True.

        Subclasses that need additional buttons override and call super():
            def _build_buttons(self) -> None:
                super()._build_buttons()
                self._buttons.append(NodeButton(self, my_pix, self._my_action))

        Icons load from icons/ folder next to the package root.
        If files are missing, Theme.icon() returns a coloured circle fallback
        so the layout holds without requiring assets to be present first.
        """
        if self._show_emoji_btn:
            if not self.data.emoji:
                from utils.pickers.IconPicker import randomling as pick_emoji
                self.data.emoji = pick_emoji()
            self._emoji_btn = EmojiButton(
                self,
                get_emoji=lambda: self.data.emoji,
                set_emoji=lambda e: setattr(self.data, 'emoji', e),
            )
            self._emoji_btn.setToolTip("More Glory")
            self._buttons.append(self._emoji_btn)
        if self._show_ports_btn:
            ports_off_pix = Theme.icon(Theme.portsIconOff, fallback_color="#7a8a9a")
            ports_on_pix  = Theme.icon(Theme.portsIconOn,  fallback_color="#9ab8c9")
            ports_btn = NodeButton(self, ports_off_pix, self._toggle_ports, ports_on_pix, toggle=True)
            ports_btn._in_confirm = self.data.ports_visible
            self._buttons.append(ports_btn)
        if self._has_depth_toggle:
            _DEPTH_BACK  = "\U0001fae4"   # 🫤
            _DEPTH_FRONT = "\U0001f62f"   # 😯
            def _depth_set(_):
                self._depth_action()
                front = getattr(self.data, 'depth_front', False)
                self._depth_btn.setToolTip("Toggle Depth, Click to send to the background." if front else "Toggle Depth, Click to bring on top of other nodes.")
            self._depth_btn = EmojiButton(
                self,
                get_emoji=lambda: _DEPTH_FRONT if getattr(self.data, 'depth_front', False) else _DEPTH_BACK,
                set_emoji=_depth_set,
            )
            front = getattr(self.data, 'depth_front', False)
            self._depth_btn.setToolTip("Toggle Depth, Click to send to the background." if front else "Toggle Depth, Click to bring on top of other nodes.")
            self._buttons.append(self._depth_btn)

        self._tint_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001f60e",   # 😎
            set_emoji=lambda _: self._toggle_node_tint(),
        )
        self._tint_btn.setToolTip("Select a new color")
        self._buttons.append(self._tint_btn)

    def _toggle_node_tint(self) -> None:
        """Cycle through ColorPicker palette colors as a temporary node highlight.
        Pressing through all colors returns to the natural default.

        If the node carries a custom node_tint that isn't yet reflected in
        _color_index (e.g. the tint was set externally after init, or the
        palette was wiped and the node's saved color is out of sync), we
        re-register it first so the cycle advances from the actual current
        color rather than snapping away and losing it.
        """
        from utils.pickers.ColorPicker import get as _pick, all_colors as _ac, register as _register
        from PySide6.QtGui import QBrush

        # Resync from data.node_tint if index fell out of sync (externally
        # set tint, palette reset, etc.) — keeps the cycle from forgetting
        # a color the node currently wears.
        saved = getattr(self.data, 'node_tint', '')
        if self._color_index == -1 and saved:
            self._color_index = _register(saved)

        colors = _ac()

        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None

        # Capture natural brush on very first press (after all subclass inits ran)
        if self._color_index == -1 and self._untinted_brush is None:
            self._untinted_brush = QBrush(self.brush())

        # Advance: -1 → 0 → 1 → … → N-1 → -1 → …
        self._color_index = 0 if self._color_index < 0 else (
            -1 if self._color_index >= len(colors) - 1 else self._color_index + 1
        )

        if hasattr(self.data, 'node_tint'):
            # Nodes that own their tint (AboutNode, ClaudeResponseNode): delegate
            # to their _apply_depth which reads data.node_tint and applies alpha.
            self.data.node_tint = _pick(self._color_index) if self._color_index >= 0 else ''
            self._apply_depth()
        else:
            # All other nodes: direct brush manipulation; restore on cycle-back.
            if self._color_index == -1:
                if self._untinted_brush is not None:
                    self.setBrush(self._untinted_brush)
            else:
                c = QColor(_pick(self._color_index))
                c.setAlpha(180)
                self.setBrush(c)
            self.update()

    def _toggle_ports(self) -> None:
        self.set_ports_visible(not self.ports_visible)
        self.data.ports_visible = self.ports_visible

    def _depth_action(self) -> None:
        self.data.depth_front = not getattr(self.data, 'depth_front', False)
        self._apply_depth()

    def _apply_depth(self) -> None:
        self.setZValue(10.0 if getattr(self.data, 'depth_front', False) else -10.0)
        self.update()

    def _position_buttons(self) -> None:
        """
        Left strip: depth toggle (and any subclass buttons); ports toggle if _show_ports_btn.
        Delete button: pinned to the top-right corner.
        Buttons compress their spacing to stay inside the node when narrow.
        """
        pad     = 4.0
        r       = self.rect()
        y       = r.top() + pad
        n       = len(self._buttons)

        if n == 0:
            return

        # Ideal stride is BUTTON_SIZE + 4px gap. If the node is too narrow,
        # compress stride so the last button's right edge stays inside.
        ideal_stride = BUTTON_SIZE + 4.0
        available    = r.width() - pad * 2
        max_stride   = (available - BUTTON_SIZE) / max(n - 1, 1)
        stride       = min(ideal_stride, max(0.0, max_stride))

        x = r.left() + pad
        for btn in self._buttons:
            btn.setPos(QPointF(x, y))
            x += stride


    def _detach_buttons(self) -> None:
        """Stop button timers before scene removal."""
        for btn in self._buttons:
            btn.detach()
        self._buttons.clear()

    def _detach_ports(self) -> None:
        """Null back-references so C++-owned port wrappers don't pin the node."""
        for p in self.input_ports:
            p.parent_node = None
        for p in self.output_ports:
            p.parent_node = None
        self.input_ports.clear()
        self.output_ports.clear()
        self.input_port  = None
        self.output_port = None

    # ─────────────────────────────────────────────────────────────────────────
    # PORTS
    # ─────────────────────────────────────────────────────────────────────────

    def _create_ports(self):
        """Instantiate ports as child items, hidden until wiring mode is enabled."""
        from nodes.Port import Port
        self.input_ports  = [Port(self, is_output=False) for _ in range(8)]
        self.output_ports = [Port(self, is_output=True)  for _ in range(8)]
        self.input_port   = self.input_ports[0]   # backwards-compat alias
        self.output_port  = self.output_ports[0]  # backwards-compat alias
        self._place_ports()
        for p in self.input_ports + self.output_ports:
            p.hide()

    def _place_ports(self):
        """
        8 ports per side — 4 corners + 4 mid-edges (N S W E).
        The Connection's _corner_tangent computes the correct inward/outward
        direction for any port position, so mid-edge ports just work.
        """
        r  = self.rect()
        w, h = r.width(), r.height()
        ox = 10   # how far outside the node edge the port sits
        positions = [
            (-ox,      -ox     ),   # TL corner
            (w + ox,   -ox     ),   # TR corner
            (-ox,      h + ox  ),   # BL corner
            (w + ox,   h + ox  ),   # BR corner
            (w / 2,    -ox     ),   # N  mid-edge
            (w / 2,    h + ox  ),   # S  mid-edge
            (-ox,      h / 2   ),   # W  mid-edge
            (w + ox,   h / 2   ),   # E  mid-edge
        ]
        for port, (cx, cy) in zip(self.input_ports, positions):
            port.setPos(cx, cy)
        for port, (cx, cy) in zip(self.output_ports, positions):
            port.setPos(cx, cy)

    def closest_input_port(self, scene_pos: 'QPointF'):
        """Return the corner input port closest to scene_pos."""
        best, best_d = self.input_ports[0], float('inf')
        for port in self.input_ports:
            p = self.mapToScene(port.pos())
            d = (p.x() - scene_pos.x()) ** 2 + (p.y() - scene_pos.y()) ** 2
            if d < best_d:
                best_d, best = d, port
        return best

    def closest_output_port(self, scene_pos: 'QPointF'):
        """Return the corner output port closest to scene_pos."""
        best, best_d = self.output_ports[0], float('inf')
        for port in self.output_ports:
            p = self.mapToScene(port.pos())
            d = (p.x() - scene_pos.x()) ** 2 + (p.y() - scene_pos.y()) ** 2
            if d < best_d:
                best_d, best = d, port
        return best

    def setRect(self, rect):
        """Keep ports anchored and wires live on resize."""
        super().setRect(rect)
        if self.output_ports:
            self._place_ports()
        if hasattr(self, '_buttons'):
            self._position_buttons()
        for conn in self.connections:
            conn.update_path()

    def set_ports_visible(self, visible: bool) -> None:
        """Show or hide all ports."""
        self.ports_visible = visible
        for p in self.input_ports + self.output_ports:
            p.setVisible(visible)

    def on_port_clicked(self, port, event) -> None:
        """Start drawing a wire from this node's output port."""
        scene = self.scene()
        if scene and hasattr(scene, 'begin_connection'):
            scene.begin_connection(self)

    # ─────────────────────────────────────────────────────────────────────────
    # MOUSE EVENTS
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """Mouse press on a BaseNode. Multiple paths:

        - **Right-click**: starts a connection wire, returns early.
        - **Left-click on resize handle**: enters resize mode. As of
          2026-05-02 this path also calls ``super().mousePressEvent``
          before returning so Qt's internal mouse-anchor state is
          initialized symmetrically with the matching
          ``super().mouseReleaseEvent``. The previous asymmetry was the
          most plausible mechanism for the "click sends node spinning
          far offscreen" bug — see the press/release balance counter
          comment in ``__init__`` for the full diagnosis.
        - **Left-click elsewhere**: arms the drag-commit dead-zone
          (Wacom phantom-motion suppression) and proceeds with the
          standard QGraphicsRectItem press handling via super().

        Press/release balance: every entry increments ``_arm_seq``
        regardless of which path is taken. The matching
        ``mouseReleaseEvent`` increments ``_release_seq``. A release
        with ``_release_seq == _arm_seq`` (i.e., no outstanding press)
        is an orphan and gets logged WARNING.
        """
        self._arm_seq += 1
        self._press_outstanding = True
        node_type = getattr(self.data, 'node_type', '?')
        scene = self.scene()

        if event.button() == Qt.RightButton:
            logger.info(
                "[base-press] %s path=connection button=right "
                "arm_seq=%d release_seq=%d (delta=%d)",
                node_type, self._arm_seq, self._release_seq,
                self._arm_seq - self._release_seq,
            )
            if scene and hasattr(scene, 'begin_connection'):
                scene.begin_connection(self)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            # Resize handle — bottom-right corner, straddling the border so
            # the cursor still catches it when it drifts a few pixels past.
            rect = self.rect()
            grip = self._resize_grip
            over = self._resize_overreach
            handle = QRectF(rect.right() - grip,
                            rect.bottom() - grip,
                            grip + over,
                            grip + over)
            if handle.contains(event.pos()):
                self._is_resizing      = True
                self._resize_start_pos  = event.pos()
                self._resize_start_rect = self.rect()
                logger.info(
                    "[base-press] %s path=resize button=left "
                    "screen=(%.1f,%.1f) scene_pos=(%.1f,%.1f) "
                    "arm_seq=%d release_seq=%d (delta=%d)",
                    node_type,
                    event.screenPos().x(), event.screenPos().y(),
                    self.scenePos().x(), self.scenePos().y(),
                    self._arm_seq, self._release_seq,
                    self._arm_seq - self._release_seq,
                )
                # Symmetry with mouseReleaseEvent's super() call. Qt's
                # internal grab-anchor / cached mouse-local-pos is set
                # up in QGraphicsItem.mousePressEvent — skipping this
                # call (as the original resize early-return did) leaves
                # super().mouseReleaseEvent running against stale
                # anchor state from a previous press, which can
                # translate the item by a huge delta on release.
                # Suspected root cause of the 2026-05-02 "node spins
                # far offscreen on click" bug. Fixed by always calling
                # super here before the early-return.
                super().mousePressEvent(event)
                event.accept()
                return
        self._is_resizing = False
        self._shake_samples.clear()
        self._shake_triggered = False
        self._shake_press_active = True
        # Arm the drag-commit dead-zone — phantom-motion suppression.
        if event.button() == Qt.LeftButton:
            self._drag_press_screen_pos = QPointF(event.screenPos())
            self._drag_committed        = False
            self._drag_suppressed_count = 0
            self._drag_suppressed_max_travel_px = 0.0
            logger.info(
                "[base-press] %s path=normal button=left "
                "screen=(%.1f,%.1f) scene_pos=(%.1f,%.1f) "
                "arm_seq=%d release_seq=%d (delta=%d) "
                "threshold=%.1fpx",
                node_type,
                event.screenPos().x(), event.screenPos().y(),
                self.scenePos().x(), self.scenePos().y(),
                self._arm_seq, self._release_seq,
                self._arm_seq - self._release_seq,
                self._DRAG_COMMIT_THRESHOLD_PX,
            )
        else:
            # Other-button press path (middle, etc.) — log so the seq
            # numbers stay traceable across non-left presses.
            logger.info(
                "[base-press] %s path=normal button=other(%s) "
                "arm_seq=%d release_seq=%d (delta=%d)",
                node_type, event.button(),
                self._arm_seq, self._release_seq,
                self._arm_seq - self._release_seq,
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            delta      = event.pos() - self._resize_start_pos
            new_width  = max(self._min_width,  self._resize_start_rect.width()  + delta.x())
            new_height = max(self._min_height, self._resize_start_rect.height() + delta.y())
            if event.modifiers() & Qt.ShiftModifier:
                ratio = self._resize_start_rect.width() / self._resize_start_rect.height()
                new_height = new_width / ratio
            self.prepareGeometryChange()
            self.setRect(QRectF(self.rect().topLeft(), QSizeF(new_width, new_height)))
            self.update()
            event.accept()
            return

        # ──────────────────────────────────────────────────────────────────────
        # Outstanding-press gate — added 2026-05-07 from forensic logs at
        # 07:45:24 onward (13 ORPHAN releases on AboutNode, commit_travel
        # up to 965 px). When no press is outstanding, any mouseMoveEvent
        # reaching us is an asymmetric Qt delivery (e.g. mouseDoubleClick-
        # Event dispatch — Qt fires press→release→doubleclick→release on
        # a double-click, so the second tap has no mousePressEvent paired
        # with its release; ImageNode's double-click-to-browse is the
        # confirmed instance, but the same shape applies to any node with
        # a mouseDoubleClickEvent override). Letting it fall through to
        # super().mouseMoveEvent translates the node by Qt's stale grab-
        # anchor delta — the "node spins far offscreen on click" symptom.
        #
        # Originally implemented 2026-05-07 as `_arm_seq <= _release_seq`
        # but that latched: once an orphan release pushed release_seq
        # past arm_seq, every subsequent press landed at delta=0 and the
        # gate stayed closed forever — the node became permanently
        # unmovable. Replaced with a boolean flag the same day after
        # forensic logs at 20:08 confirmed the latch (25 cascading
        # ORPHAN warnings on a single image node, all from one underlying
        # asymmetric dispatch). A boolean is binary, cannot drift,
        # cannot latch.
        #
        # The orphan-release counter in mouseReleaseEvent stays as the
        # canary; this gate just stops the translate from happening.
        if not self._press_outstanding:
            event.accept()
            return

        # Drag-commit dead zone — Wacom phantom-motion suppression. See
        # _DRAG_COMMIT_THRESHOLD_PX. Until cumulative cursor travel from
        # press exceeds the threshold, eat the event without translating
        # the item or feeding the shake detector.
        if not self._drag_committed:
            cur = event.screenPos()
            dx = cur.x() - self._drag_press_screen_pos.x()
            dy = cur.y() - self._drag_press_screen_pos.y()
            travel_px = (dx * dx + dy * dy) ** 0.5
            if travel_px < self._DRAG_COMMIT_THRESHOLD_PX:
                self._drag_suppressed_count += 1
                if travel_px > self._drag_suppressed_max_travel_px:
                    self._drag_suppressed_max_travel_px = travel_px
                logger.log(5,
                    "[base-drag-gate] %s SUPPRESS #%d travel=%.2fpx (threshold=%.1f) "
                    "screen=(%.1f,%.1f) scene_pos=(%.1f,%.1f) "
                    "arm_seq=%d release_seq=%d",
                    getattr(self.data, 'node_type', '?'),
                    self._drag_suppressed_count, travel_px,
                    self._DRAG_COMMIT_THRESHOLD_PX,
                    cur.x(), cur.y(),
                    self.scenePos().x(), self.scenePos().y(),
                    self._arm_seq, self._release_seq)
                event.accept()
                return
            self._drag_committed = True
            logger.info(
                "[base-drag-gate] %s COMMIT after %d suppressed events "
                "(max travel during suppression=%.2fpx, commit travel=%.2fpx) — "
                "drag begins. arm_seq=%d release_seq=%d",
                getattr(self.data, 'node_type', '?'),
                self._drag_suppressed_count,
                self._drag_suppressed_max_travel_px, travel_px,
                self._arm_seq, self._release_seq)

        super().mouseMoveEvent(event)
        if not self._is_resizing:
            self._track_shake()

    # ─────────────────────────────────────────────────────────────────────────
    # SHAKE-TO-DETACH / SHAKE-TO-DELETE
    # ─────────────────────────────────────────────────────────────────────────

    _SHAKE_SAMPLE_INTERVAL = 0.03   # seconds between position samples
    _SHAKE_WINDOW          = 0.40   # seconds of history to keep
    _SHAKE_MIN_DELTA       = 8.0    # screen-px — ignore jitter smaller than this
    _SHAKE_REVERSALS       = 3      # direction changes needed to trigger

    # Drag-commit dead zone — Wacom phantom-motion suppression. Cumulative
    # cursor travel from press must exceed this threshold (in screen-px)
    # before mouseMoveEvent translates the node and feeds shake samples.
    # Real human drags blow past 12 screen-px in a single event; phantom
    # synthesized cursor settling stays under it. See __init__ note.
    _DRAG_COMMIT_THRESHOLD_PX = 12.0

    def _track_shake(self) -> None:
        """Sample position during drag at ~30ms intervals and check for shake.

        Gated on _shake_press_active so stray move events after another node's
        removal can't trigger shake without a proper press first.
        Also gated on a module-level cooldown that blocks cascade-deletes when
        Qt transfers the mouse grab after the previous node was removed.
        """
        if _shake_cooling_down():
            return
        if not self._shake_press_active:
            return
        if self._shake_triggered:
            return
        now = _time.monotonic()
        if self._shake_samples and (now - self._shake_samples[-1][0]) < self._SHAKE_SAMPLE_INTERVAL:
            return
        self._shake_samples.append((now, QPointF(self.scenePos())))
        cutoff = now - self._SHAKE_WINDOW
        self._shake_samples = [(t, p) for t, p in self._shake_samples if t >= cutoff]
        if self._detect_shake():
            self._shake_triggered = True
            self._shake_detach()

    def _detect_shake(self) -> bool:
        """Count direction reversals on either axis — 3+ in the window = shake.

        Deltas are converted to screen-space pixels so the same physical effort
        is required regardless of zoom level.
        """
        pts = self._shake_samples
        if len(pts) < 4:
            return False
        zoom = 1.0
        scene = self.scene()
        if scene and scene.views():
            zoom = getattr(scene.views()[0], 'current_zoom', 1.0)
        for axis in (0, 1):   # 0 = x, 1 = y
            reversals = 0
            prev_d = 0.0
            for i in range(1, len(pts)):
                d = (pts[i][1].x() - pts[i-1][1].x()) if axis == 0 \
                    else (pts[i][1].y() - pts[i-1][1].y())
                # Compare in screen pixels — scene delta × zoom
                if abs(d * zoom) < self._SHAKE_MIN_DELTA:
                    continue
                if prev_d != 0.0 and d * prev_d < 0:
                    reversals += 1
                prev_d = d
            if reversals >= self._SHAKE_REVERSALS:
                return True
        return False

    def _shake_detach(self) -> None:
        """Shake while connected → detach wires and bridge the gap.
        Shake while unconnected → dissolve the node with a particle burst.
        Multiple nodes selected → purge entire selection."""
        scene = self.scene()
        if scene:
            # Pick up any node-like peer in the selection — BaseNode *and*
            # StickerNode (2026-04-18 root-split).  The duck-type check keeps
            # future node roots working without another edit here.
            selected = [item for item in scene.selectedItems()
                        if item is not self
                        and hasattr(item, 'connections')
                        and hasattr(item, '_prepare_for_removal')]
            if selected:
                self._shake_delete_group(selected)
                return

        if self.connections:
            self._shake_detach_wires()
        else:
            self._shake_delete()

    def _shake_detach_wires(self) -> None:
        """Detach all wires from this node and bridge the gap behind it."""
        scene = self.scene()
        if not scene or not self.connections:
            return
        from graphics.Connection import Connection

        sources = [c.start_node for c in self.connections
                   if c.end_node is self and c.start_node is not None]
        targets = [c.end_node   for c in self.connections
                   if c.start_node is self and c.end_node is not None]

        for conn in list(self.connections):
            conn._glide_timer.stop()
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other is not None and other is not self:
                try:    other.connections.remove(conn)
                except ValueError: pass
            conn.start_node = None
            conn.end_node   = None
            if conn.scene():
                scene.removeItem(conn)
        self.connections.clear()

        from graphics.Particles import sprinkle
        sprinkle(scene, self.mapToScene(self.rect().center()), count=8000)

        for src in sources:
            for tgt in targets:
                if src is tgt:
                    continue
                new_conn = Connection(src, tgt)
                scene.addItem(new_conn)
                new_conn.update_path()

    def _quiet_for_shake(self) -> None:
        """Hook for subclasses to synchronously disconnect per-frame signals
        (scrollbars, cross-node callbacks) before the deferred-removeItem
        window opens.  Base: no-op.  StickerNode overrides to disconnect
        viewport tracking; add similar overrides in any node type that
        wires peer-level signals outside the standard NodeBehaviour set."""
        return

    def _shake_delete(self) -> None:
        """Dissolve this node with a particle burst. Deferred to mouseRelease
        so the mouse grab releases cleanly before the scene removes the item."""
        scene = self.scene()
        if not scene:
            return
        # Snapshot the node data before deletion so the sidebar can restore it.
        try:
            scene._last_deleted = self.to_dict()
        except Exception:
            pass
        # Synchronous pre-shake quieting.  Signals left live between here
        # and the deferred removeItem have tripped 0xc0000409 fastfails
        # in the past (see Node Cleanup Compliance 2026-04-18).
        try:
            self._quiet_for_shake()
        except Exception:
            pass
        _arm_shake_cooldown()
        from graphics.Particles import sprinkle, orbital_burst, shake_mode
        center = self.mapToScene(self.rect().center())
        if shake_mode == "orbital":
            orbital_burst(scene, center)
        else:
            sprinkle(scene, center, count=8000)
        self._pending_shake_delete = True

    def _shake_delete_group(self, others: list['BaseNode']) -> None:
        """Dissolve this node plus all other selected nodes.

        The shaken node (self) is deferred to mouseRelease as usual.
        The other selected nodes are removed directly via deferred
        QTimer since they don't hold an active mouse grab.
        """
        scene = self.scene()
        if not scene:
            return

        _arm_shake_cooldown()
        from graphics.Particles import sprinkle, orbital_burst, shake_mode

        # Particles on the shaken node
        center = self.mapToScene(self.rect().center())
        if shake_mode == "orbital":
            orbital_burst(scene, center)
        else:
            sprinkle(scene, center, count=8000)

        # Mark self for deferred delete (handled by mouseReleaseEvent)
        self._pending_shake_delete = True
        try:
            self._quiet_for_shake()
        except Exception:
            pass

        # Remove connections between deleted nodes and external nodes,
        # then deferred-remove each selected node.
        doomed = set(others) | {self}
        # Peer-paint-during-burst guard: raise a scene-level counter that
        # tells surviving peers (glide ticks, bg animations, etc.) to skip
        # their per-frame repaint work while the removal queue drains.
        # Counter, not flag, so nested/overlapping bursts compose safely.
        # The release is deferred twice: once behind the last removeItem
        # tick, then once more so any repaint scheduled by those removes
        # also sees the quiet flag before it is lowered.
        scene._bulk_removing = getattr(scene, '_bulk_removing', 0) + 1
        for node in others:
            try:
                node._quiet_for_shake()
            except Exception:
                pass
            # Remove wires that connect to nodes outside the doomed set
            for conn in list(node.connections):
                other_end = conn.end_node if conn.start_node is node else conn.start_node
                if other_end not in doomed:
                    if other_end is not None:
                        try:    other_end.connections.remove(conn)
                        except ValueError: pass
                conn.start_node = None
                conn.end_node   = None
                if conn.scene():
                    scene.removeItem(conn)
            node.connections.clear()

            node.setSelected(False)
            node.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
            # Capture the scene-space rect NOW — after removeItem the node
            # can't map to scene, and without the invalidate the viewport
            # keeps a ghost pixel band for several seconds while the
            # particle burst chews through paint events.
            try:
                ghost_rect = node.mapRectToScene(node.boundingRect())
            except RuntimeError:
                ghost_rect = None
            def _deferred(n=node, sc=scene, r=ghost_rect):
                # Widen catch to Exception.  Previously RuntimeError-only
                # meant an unexpected AttributeError/TypeError would
                # propagate, break this callback, and leave the node
                # alive in the scene (2026-04-18 ghost).  Whatever goes
                # wrong here, the removal intent must not be abandoned
                # — the straggler sweep in _release_bulk catches anything
                # this leg missed.
                try:
                    sc.removeItem(n)
                except Exception:
                    pass
                if r is not None:
                    try:
                        sc.invalidate(r)
                    except Exception:
                        pass
            QTimer.singleShot(0, _deferred)

        def _release_bulk(sc=scene):
            sc._bulk_removing = max(0, getattr(sc, '_bulk_removing', 1) - 1)
            if sc._bulk_removing == 0:
                # Straggler sweep: any node whose demolish crew already
                # ran (`_removal_done == True`) but which is somehow
                # still in the scene is a stranded survivor.  A
                # deferred removeItem call that silently failed, an
                # exception in the callback, a bookkeeping mismatch
                # — whatever the cause, the intent was clear and the
                # visible result is a node that looks alive but whose
                # teardown contract is already complete.  Force-remove.
                for item in list(sc.items()):
                    if getattr(item, '_removal_done', False):
                        try:
                            sc.removeItem(item)
                        except Exception:
                            pass
                # Nuclear repaint: force a full viewport refresh to
                # catch any paint residue the per-node invalidates may
                # have missed under heavy bulk load.  Qt's paint
                # scheduler can run mid-batch when hundreds of
                # removeItems fire in one tick and coalesce the
                # invalidates imperfectly.  A single paint, after the
                # burst, marginal cost negligible.
                try:
                    for _view in sc.views():
                        _view.viewport().update()
                except Exception:
                    pass
        def _defer_release(sc=scene):
            QTimer.singleShot(0, _release_bulk)
        QTimer.singleShot(0, _defer_release)

    def mouseReleaseEvent(self, event):
        """Mouse release on a BaseNode. Logs the release with full
        balance/state context, detects orphan releases (release
        without a corresponding press through ``mousePressEvent``),
        runs the drag-gate post-mortem, syncs geometry back to data,
        and resets the drag-gate state so the next gesture starts
        clean regardless of how it arrives.

        Orphan release detection — added 2026-05-02 — fires WARNING
        when ``_release_seq + 1 > _arm_seq``, i.e. Qt sent us a
        release for a press we never saw through ``mousePressEvent``.
        Should be unreachable now that the resize early-return path
        also calls super, but the check is cheap and surfaces any
        future asymmetric-gesture path immediately.

        State reset at the end — added 2026-05-02 — drops
        ``_drag_committed`` / ``_drag_suppressed_count`` /
        ``_drag_suppressed_max_travel_px`` / ``_drag_press_screen_pos``
        back to defaults after the post-mortem log captures their
        gesture-end values. Belt-and-braces against future code paths
        leaving stale drag-gate state visible to subsequent gestures.
        """
        self._release_seq += 1
        self._press_outstanding = False
        node_type = getattr(self.data, 'node_type', '?')
        was_resizing = self._is_resizing

        # Orphan-release detection — release_seq should never exceed
        # arm_seq. If it does, mouseReleaseEvent was called without a
        # matching mousePressEvent through this method (e.g., via Qt's
        # mouseDoubleClickEvent dispatch where the second tap fires
        # release without a paired press). Logged WARNING so it surfaces
        # in normal log scrape, then immediately re-synced so a single
        # asymmetric dispatch fires exactly one warning instead of
        # latching into a cascade.
        is_orphan = self._release_seq > self._arm_seq
        if is_orphan:
            logger.warning(
                "[base-release] %s ORPHAN release — no preceding press "
                "through mousePressEvent. button=%s was_resizing=%s "
                "arm_seq=%d release_seq=%d. Likely an asymmetric Qt "
                "dispatch (mouseDoubleClickEvent or similar). Re-syncing "
                "release_seq to arm_seq so the next gesture starts balanced.",
                node_type, event.button(), was_resizing,
                self._arm_seq, self._release_seq,
            )
            # Self-heal: pull release_seq back to arm_seq so the next
            # press/release pair lands as delta=1 instead of compounding
            # the drift. Prior implementation (without this reset) saw
            # a single double-click cascade into 25 false-positive WARNs
            # in one session because the seqs stayed permanently shifted.
            self._release_seq = self._arm_seq

        self._is_resizing = False
        self._shake_press_active = False

        # Drag-gate post-mortem — captures the gesture's end state.
        # Promoted to INFO 2026-05-02 (was TRACE) so press/release
        # pairs are always visible in default logs.
        if event.button() == Qt.LeftButton:
            if not self._drag_committed and self._drag_suppressed_count > 0:
                logger.info(
                    "[base-release] %s RELEASE without commit — gate suppressed "
                    "%d phantom motion events (max travel=%.2fpx, threshold=%.1fpx). "
                    "was_resizing=%s arm_seq=%d release_seq=%d. "
                    "If this happened on a stationary touch, the gate did its job.",
                    node_type,
                    self._drag_suppressed_count,
                    self._drag_suppressed_max_travel_px,
                    self._DRAG_COMMIT_THRESHOLD_PX,
                    was_resizing, self._arm_seq, self._release_seq,
                )
            else:
                logger.info(
                    "[base-release] %s button=left committed=%s suppressed=%d "
                    "max_travel=%.2fpx was_resizing=%s arm_seq=%d release_seq=%d",
                    node_type,
                    self._drag_committed,
                    self._drag_suppressed_count,
                    self._drag_suppressed_max_travel_px,
                    was_resizing, self._arm_seq, self._release_seq,
                )
        else:
            logger.info(
                "[base-release] %s button=%s was_resizing=%s "
                "arm_seq=%d release_seq=%d",
                node_type, event.button(), was_resizing,
                self._arm_seq, self._release_seq,
            )

        # Sync geometry back to data after a resize or move.
        self.data.x      = self.pos().x()
        self.data.y      = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        if was_resizing:
            # Round-trip diagnostic — paired with the auto-fit logs in
            # TreeNode/WarmNode. "I set N, user landed at M." Comparing
            # N and M tells us the deliberate-target-vs-desired gap.
            # Kept as DEBUG for future node-width debugging sessions —
            # flip log level up to INFO temporarily if investigating.
            logger.debug(
                "[resize-end] %s title=%r final rect w=%.0f h=%.0f  data.width=%.0f",
                type(self).__name__, getattr(self.data, 'title', ''),
                self.rect().width(), self.rect().height(), self.data.width,
            )
        super().mouseReleaseEvent(event)

        # Drag-gate state reset — added 2026-05-02 alongside the
        # press/release balance counters. The post-mortem log above
        # captured the values that ended this gesture; from this point
        # on, no gesture should rely on these values until a fresh ARM.
        # Resetting here defends against any future asymmetric path
        # (e.g., a release that fires without a press through
        # mousePressEvent) reading values left over from a previous
        # click — the symptom mechanism we suspected for the
        # "node spins far offscreen on click" bug class.
        self._drag_committed                = False
        self._drag_suppressed_count         = 0
        self._drag_suppressed_max_travel_px = 0.0
        self._drag_press_screen_pos         = QPointF()
        # Release the scene mouse grab only if THIS item still holds it.
        # ungrabMouse() is NOT a safe no-op on non-grabbers — it touches Qt's
        # internal dispatch state and can break selection on neighboring items
        # that received a transferred grab after a shake-delete.
        if not event.buttons():
            scene = self.scene()
            if scene and scene.mouseGrabberItem() is self:
                self.ungrabMouse()
        # Deferred shake-delete — pre-clear dispatch state NOW, then schedule
        # the actual removeItem for the next event-loop tick.  Zeroing flags
        # and selection immediately prevents Qt from routing any mouse events
        # to this zombie during the deferred-removal window.
        if self._pending_shake_delete:
            self._pending_shake_delete = False
            scene = self.scene()
            if scene:
                self.setSelected(False)
                # Hide + mark no-contents BEFORE any further state mutation.
                # Qt's paint dispatch consults visibility and the
                # ItemHasNoContents flag at item-iteration time; setting
                # both here pulls the node out of the paint list
                # immediately, so no subsequent paint pass can reach a
                # being-torn-down QGraphicsItem (fixes a Qt6Widgets
                # 0xc0000005 access violation observed on the second
                # shake in a quick sequence — the deleted node was still
                # being iterated by the paint dispatch between setFlags
                # clearing the interaction flags and _deferred_remove
                # calling removeItem one event-loop tick later).
                self.setVisible(False)
                # GraphicsItemFlags with ItemHasNoContents signals to Qt
                # that paint() should never be called on this item — even
                # if invalidate rects cover its former geometry.
                self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemHasNoContents)
                # Peer-paint-during-burst guard: raise the scene-level
                # counter BEFORE particles and removal cascade so surviving
                # peers (Connection glide ticks, NodeBehaviour pulses,
                # NodeButton, StickerNode viewport tracking) skip their
                # per-frame repaint work while the single-node removal
                # drains.  The group-shake path already does this at
                # _shake_delete_group; the single-node path was missing it,
                # which turned fine for isolated deletions but cascaded badly
                # when a node sat in a long chain (deleting one edge of a
                # ~100-node TextNode split chain at 12:09:36 — crash
                # signature 0xC0000409, no Python traceback, indicating a
                # peer paint path dereferenced dying state).  Counter, not
                # flag, so overlapping single-deletes compose safely.
                scene._bulk_removing = getattr(scene, '_bulk_removing', 0) + 1
                # Capture the ghost rect before removal so we can force a
                # repaint of that region; otherwise an 8000-particle burst
                # saturates the event loop and the deleted node lingers
                # visibly for several seconds (2026-04-18 GitNode ghost).
                try:
                    ghost_rect = self.mapRectToScene(self.boundingRect())
                except RuntimeError:
                    ghost_rect = None
                def _deferred_remove(node=self, sc=scene, r=ghost_rect):
                    # All catches widened to Exception after the
                    # 2026-04-18 chain-leftover ghost — a non-RuntimeError
                    # in any leg must not abandon the removal intent.
                    try:
                        if sc.mouseGrabberItem() is node:
                            node.ungrabMouse()
                    except Exception:
                        pass
                    try:
                        sc.removeItem(node)
                    except Exception:
                        pass
                    # Straggler double-check: if removeItem quietly failed
                    # and the node is still in the scene with demolish
                    # already done, one more removal attempt.  The demolish
                    # contract is complete either way; the visual state
                    # must match.
                    try:
                        if getattr(node, '_removal_done', False) and node.scene() is sc:
                            sc.removeItem(node)
                    except Exception:
                        pass
                    if r is not None:
                        try:
                            sc.invalidate(r)
                        except Exception:
                            pass
                    # Force a viewport repaint alongside the rect
                    # invalidate.  Even for a single-node shake-delete,
                    # the paint scheduler can occasionally leave the
                    # node's border chrome on the back buffer.
                    try:
                        for _view in sc.views():
                            _view.viewport().update()
                    except Exception:
                        pass
                def _release_bulk(sc=scene):
                    # Lower the quiescence counter two event-loop ticks
                    # after removeItem so any repaint scheduled by the
                    # tail end of the removal still sees the flag raised.
                    # Mirrors the release pattern in _shake_delete_group.
                    sc._bulk_removing = max(0, getattr(sc, '_bulk_removing', 1) - 1)
                    if sc._bulk_removing == 0:
                        # Straggler sweep: any node whose demolish crew
                        # already ran but somehow stayed in the scene
                        # gets a forced removal — same belt-and-braces
                        # as _shake_delete_group's release.
                        for item in list(sc.items()):
                            if getattr(item, '_removal_done', False):
                                try:
                                    sc.removeItem(item)
                                except Exception:
                                    pass
                        # Single final viewport repaint on release.
                        try:
                            for _view in sc.views():
                                _view.viewport().update()
                        except Exception:
                            pass
                QTimer.singleShot(0, _deferred_remove)
                # Release AFTER the particle fade window.  8000 sprinkle
                # particles linger + fade over ~500ms; peer paint
                # invalidations caused by particle rendering (especially
                # at extreme zoom where a particle cluster covers a
                # large chunk of the viewport) should see the quiescence
                # flag raised throughout.  Previously the release fired
                # two event-loop ticks (~32ms) after removeItem — too
                # short for the zoom-out-then-zoom-in repro where
                # viewTransformed cascades leave the paint scheduler
                # backed up and straggling paints land on freshly-
                # severed state after the flag was already lowered.
                # 500ms matches the particle fade and gives the paint
                # queue room to drain.
                QTimer.singleShot(500, _release_bulk)


    def _try_splice_into_wire(self) -> None:
        """
        Check if this node's center sits on a wire it isn't already part of.
        If so, remove the original wire and create two new ones:
            original.start → self → original.end
        """
        scene = self.scene()
        if not scene:
            return
        from graphics.Connection import Connection

        node_rect = self.mapRectToScene(self.rect())
        for item in scene.items(node_rect):
            if not isinstance(item, Connection):
                continue
            if item.start_node is self or item.end_node is self:
                continue
            src = item.start_node
            tgt = item.end_node
            if src is None or tgt is None:
                continue

            # Tear down the original wire
            item._glide_timer.stop()
            try:    src.connections.remove(item)
            except ValueError: pass
            try:    tgt.connections.remove(item)
            except ValueError: pass
            item.start_node = None
            item.end_node   = None
            scene.removeItem(item)

            # Splice: src → self → tgt
            conn_in  = Connection(src, self)
            scene.addItem(conn_in)
            conn_in.update_path()

            conn_out = Connection(self, tgt)
            scene.addItem(conn_out)
            conn_out.update_path()
            break   # one splice per drop

    def mouseDoubleClickEvent(self, event):
        """Toggle button shelf on top-strip double-click; subclasses call super() for this."""
        if event.pos().y() < self.rect().top() + self._anim_top_offset:
            self._toggle_shelf()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _toggle_shelf(self) -> None:
        """Animate the button row in or out."""
        self._buttons_visible = not self._buttons_visible
        self._shelf_anim.stop()
        if self._buttons_visible:
            self._shelf_anim.setStartValue(self._anim_top_offset)
            self._shelf_anim.setEndValue(self._BUTTON_ZONE_H)
        else:
            for btn in self._buttons:
                btn.hide()
            self._shelf_anim.setStartValue(self._anim_top_offset)
            self._shelf_anim.setEndValue(self._HIDDEN_TOP_OFFSET)
        self._shelf_anim.start()

    def _on_shelf_tick(self, value: float) -> None:
        self._anim_top_offset = value
        self.update()

    def _on_shelf_done(self) -> None:
        if self._buttons_visible:
            self._position_buttons()
            for btn in self._buttons:
                btn.show()

    # ─────────────────────────────────────────────────────────────────────────
    # FILE DIALOG HELPER
    # ─────────────────────────────────────────────────────────────────────────

    def _lower_window(self) -> 'QMainWindow | None':
        """Drop always-on-top before opening a file dialog so it isn't hidden."""
        views = self.scene().views() if self.scene() else []
        win = views[0].window() if views else None
        if win:
            self._saved_flags = win.windowFlags()
            win.setWindowFlags(self._saved_flags & ~Qt.WindowStaysOnTopHint)
            win.show()
        return win

    def _raise_window(self, win=None) -> None:
        """Restore always-on-top after the dialog closes."""
        if win and hasattr(self, '_saved_flags'):
            win.setWindowFlags(self._saved_flags)
            win.show()
            win.raise_()

    @contextmanager
    def _dialog_choreography(self):
        """Run a modal dialog with Intricate's standard choreography.

        Drops always-on-top, rolls curtains up if currently down, focuses
        the main window so the dialog spawns with a real owner HWND in
        front, then restores curtains and always-on-top on exit. Yields
        the main window (or None if there is no scene/view) so the caller
        can pass it as the dialog's parent — important on Windows so the
        native file picker doesn't drift behind another desktop window.

        Three settle-points are load-bearing for Windows focus reliability:

          1. **Drain pending events immediately after `_lower_window()`.**
             `setWindowFlags` inside `_lower_window()` recreates the
             native HWND on Windows.  Without an immediate drain, the
             recreation events stack up behind the curtain animation
             and dialog spawn — the dialog ends up parented to a not-
             yet-foregrounded HWND and the OS silently refuses to
             surface it.  On a fresh session this manifests as the
             first-ever file-browser click rolling the curtains up
             but the dialog never appearing; subsequent clicks succeed
             because the HWND is now warm.  Draining here breaks the
             stack-up so the HWND is settled before any further
             choreography begins.
          2. **Curtain animation must finish before yielding.** Without
             waiting, the dialog spawns mid-geometry-transition (the
             curtain roll is ~539 ms).  Windows refuses to promote the
             dialog to foreground while its parent HWND is in animated
             flight, so the dialog opens behind whatever else holds the
             foreground state.  We block on `curtain_anim.finished` via
             a nested QEventLoop so the parent is fully settled when the
             dialog appears.
          3. **Drain the event queue after activate/raise.**
             `activateWindow()` is a request that may not land until
             pending events drain.  `processEvents()` flushes pending
             events so the activation actually takes effect before the
             dialog spawns.

        Without these settle-points, the focus loss is intermittent —
        sometimes the race resolves favourably, sometimes the dialog
        ends up under another desktop app, and on a fresh session the
        first dialog can fail to surface entirely.

        Usage:
            with self._dialog_choreography() as mw:
                path, _ = QFileDialog.getOpenFileName(mw, "Title", start, filter)
                # use path...
        """
        win = self._lower_window()
        # Settle (1): drain HWND-recreation aftermath before further
        # choreography stacks events on top of it.  See docstring above.
        QApplication.processEvents()
        was_collapsed = False
        mw = None
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
                    was_collapsed = True
                    # Block until the curtain roll finishes — see (2) above.
                    anim = getattr(mw, 'curtain_anim', None)
                    if anim is not None and anim.state() == QAbstractAnimation.State.Running:
                        loop = QEventLoop()
                        anim.finished.connect(loop.quit)
                        loop.exec()
        except Exception:
            pass
        if mw is not None:
            try:
                mw.activateWindow()
                mw.raise_()
                # Drain pending events so the activation actually
                # lands before the dialog spawns — see (3) above.
                QApplication.processEvents()
            except Exception:
                pass
        try:
            yield mw
        finally:
            if was_collapsed and mw is not None:
                try:
                    mw.toggle_curtains()
                except Exception:
                    pass
            self._raise_window(win)

    def hoverEnterEvent(self, event):
        if self.behaviour:
            self.behaviour.on_hover_enter()
        self.current_pen = self.hover_pen
        self.setPen(self.current_pen)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.behaviour:
            self.behaviour.on_hover_leave()
        self.current_pen = self.normal_pen
        self.setPen(self.current_pen)
        self.update()
        super().hoverLeaveEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def boundingRect(self):
        """Extend bounding rect to include shadow margin AND the resize
        overreach on the bottom-right. Qt uses boundingRect as a fast-cull
        check before consulting shape(), so any zone of shape() that lives
        outside boundingRect is unreachable by clicks. The right/bottom
        extension is the larger of shadow margin and resize overreach so
        the resize hit zone past the corner actually fires."""
        over = self._resize_overreach
        right_bottom_pad = max(_SHADOW_MARGIN, over)
        return self.rect().adjusted(
            -_SHADOW_MARGIN, -_SHADOW_MARGIN,
             right_bottom_pad,  right_bottom_pad,
        )

    def shape(self):
        """Hit-test shape matches the visible node border, plus a lobe at
        the bottom-right corner so the resize grip remains catchable when
        the cursor drifts a few pixels past the visible edge.

        Fill rule MUST be WindingFill. The default OddEvenFill treats the
        overlap between the rounded body and the corner lobe as a *hole*
        — points inside both regions cancel to "outside" under odd-even
        crossings. With a small lobe (e.g. grip=16, over=6) the hole is
        a sliver in the corner-radius cut-off and goes unnoticed; with a
        VideoNode-sized 128×128 lobe centered on the corner, the hole
        eats the entire inside-the-body resize zone and clicks there
        route to nothing. WindingFill counts each clockwise crossing
        positively, so overlapping clockwise sub-paths add up rather
        than cancel.
        """
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        path.addRoundedRect(self.rect(), self.round_radius, self.round_radius)
        r = self.rect()
        grip = self._resize_grip
        over = self._resize_overreach
        path.addRect(QRectF(
            r.right() - grip,
            r.bottom() - grip,
            grip + over,
            grip + over,
        ))
        return path

    # Aerial = navigation altitude. Below this LOD, the node drops its entire
    # interaction layer — chrome, paint_content (title + body text), ports,
    # selection ring all skip — and renders a single thin cream strip where
    # body text would live. Mental model: at this zoom the canvas is being
    # read as a map for the next swoosh-down, not as an interactive surface.
    #
    # Threshold story (read-the-history bookmark):
    #   2026-05-02 v1: 0.15 across the board. Visible flip at moderate aerial
    #                  because Qt's natural sub-pixel text rendering still
    #                  produced content-distinguishing texture there.
    #   2026-05-02 v2: lowered to 0.07 — the "camera trick" altitude where
    #                  natural rendering smears into a generic blob and the
    #                  strip becomes a faithful stand-in.
    #   2026-05-02 v3: with ZOOM_MIN extended from 0.03 to 0.01, the user
    #                  found themselves zooming all the way to the floor
    #                  comfortably and wanted natural rendering to dominate
    #                  for longer. v3 narrows the strip's role to a pure
    #                  visibility floor: 0.0 default disables it for every
    #                  node type, and only WarmNode opts in by overriding
    #                  AERIAL_LOD_THRESHOLD = 0.03 (text-only nodes are
    #                  the ones that actually fade at extreme zoom; other
    #                  node types carry visual content that reads on its
    #                  own at any altitude).
    #
    # Subclasses opt in by overriding this value with the LOD they want as
    # their aerial threshold. Default 0.0 means `lod < threshold` is never
    # true for valid LOD values — aerial mode is off.
    #
    # NB: Connection._AERIAL_LOD_THRESHOLD stays at 0.15 — split deliberately.
    # Wires are sub-pixel by 0.15 anyway (no visible ribbon at that altitude),
    # so the wire-skip is invisible and reclaims the second-largest paint
    # cost (Bezier evaluation across many wires per zoom frame) for the
    # whole 0.15-down band where nodes are still painting natural pipeline.
    AERIAL_LOD_THRESHOLD = 0.0

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Aerial-zoom shortcut. levelOfDetailFromTransform reads the painter's
        # current scene→device scale (the view's zoom factor for an unrotated
        # node), so no cross-object lookup or signal plumbing is needed.
        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
        if lod < self.AERIAL_LOD_THRESHOLD:
            rect = self.rect()
            pad_x = 8.0
            strip_h = max(rect.height() * 0.3, 4.0)
            strip_y = rect.center().y() - strip_h / 2
            painter.fillRect(
                QRectF(rect.x() + pad_x, strip_y,
                       rect.width() - 2 * pad_x, strip_h),
                QColor(Theme.textPrimary),
            )
            painter.restore()
            return

        # Selection pen overrides current pen
        pen = self.selected_pen if self.isSelected() else self.current_pen
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), self.round_radius, self.round_radius)

        # Hand off to subclass for type-specific content
        self.paint_content(painter)

        painter.restore()

    _BUTTON_ZONE_H   = 40.0   # px reserved for the button strip (4 pad + 32 button + 4 gap)
    _HIDDEN_TOP_OFFSET = 8.0  # px top margin when shelf is collapsed — subclass override for tighter nodes (e.g. AboutNode)
    _CONTENT_PAD     = 15.0   # horizontal padding for title/body text
    _TITLE_HEIGHT    = 40.0   # rect height allocated for title text
    _BODY_OFFSET     = 36.0   # px below title top where body text starts
    # Right-side padding for the title rect. None = symmetric with the left
    # pad (Theme.nodeTextPaddingLeft). Subclasses that auto-fit the node
    # width to the title (WarmNode, TreeNode) override to a smaller int so
    # the title can hug the right edge — left pad stays at the theme value,
    # right pad is the tight number the subclass sets. Fit formulas must
    # match exactly: needed = title_w + pad + _TITLE_RIGHT_PAD.
    _TITLE_RIGHT_PAD: int | None = None
    _TITLE_FONT      = "Chandler42"
    _TITLE_STYLE     = "Italic"          # Chandler42's script-italic Medium (1843.otf — see pretty_widgets.utils.fonts)
    _TITLE_FONT_BUMP = 6      # added to Theme.aboutFontSize for title
    _BODY_FONT       = "Lato"
    _BODY_FONT_BUMP  = -1     # added to Theme.aboutFontSize for body

    def _content_top(self) -> float:
        """Y offset from node top to title text — the canonical spacing all nodes use.

        Tracks the animated shelf offset so the title slides with the button row.
        Subclasses that override paint_content should use this instead of computing
        their own title position.
        """
        return self._anim_top_offset + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop

    def _body_top(self) -> float:
        """Y offset from node top to body text — title top + body offset."""
        return self._content_top() + self._BODY_OFFSET

    def _title_rect(self) -> QRectF:
        """Text area below the button strip."""
        r   = self.rect()
        pad = Theme.nodeTextPaddingLeft
        right_pad = pad if self._TITLE_RIGHT_PAD is None else self._TITLE_RIGHT_PAD
        top = self._content_top()
        return QRectF(
            r.left() + pad,
            r.top() + top,
            r.width() - pad - right_pad,
            r.height() - self._anim_top_offset,
        )

    def _measure_title_width(self) -> float:
        """Painted width of the current title, measured via QPainterPath
        and the EXACT same QFont construction the default paint_content
        uses (line 1275: `QFont(Theme.aboutFontFamily, Theme.aboutFontSize)`
        + setStyleName(self._TITLE_STYLE)).

        The historical bug this replaces: we were measuring with
        `Theme.aboutFontSize + self._TITLE_FONT_BUMP` (18pt when the
        user has [node.about] font_size = 12 in settings.toml), but
        the default paint renders without the bump (12pt). That's a
        1.5× overmeasurement, which propagates straight into the fit
        formula — long titles get 1.5× more node width than they need.
        See git history 2026-04-22 for the chase that found this.

        QPainterPath also avoids QFontMetrics' known friction with
        non-monospaced fonts (Chandler42 being the reference case).

        Subclasses that override paint_content with a different title
        font size (e.g., AudioNode paints with +_TITLE_FONT_BUMP) must
        override _measure_title_width to match — the measurement has
        to track the paint, not the other way around.
        """
        if not self.data.title:
            return 0.0
        from PySide6.QtGui import QFont, QPainterPath
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        font.setStyleName(self._TITLE_STYLE)
        path = QPainterPath()
        path.addText(0, 0, font, self.data.title)
        return path.boundingRect().width()

    def paint_content(self, painter: QPainter):
        """
        Specialist paint handoff — override in subclasses.

        Called after the shell (background + border) is painted.
        Painter is in node-local coordinates.

        Default implementation draws the title below the button strip.
        The emoji is rendered by the EmojiButton in the button row.
        Subclasses that need type-specific content override this entirely
        (no super() needed), or call super() to inherit the title row.
        """
        painter.save()
        _f = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        _f.setStyleName(self._TITLE_STYLE)
        painter.setFont(_f)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        painter.drawText(self._title_rect(), Qt.AlignLeft | Qt.AlignTop, self.data.title)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self):
        """
        Push current visual state back into NodeData before serialization.

        Called before to_dict() so position and size are always current.
        Subclasses with additional visual state override this and call super().

        Every field uses getattr-with-default so sync_data cannot raise on
        a partially-initialised node — critical for the clipboard copy path,
        which cannot afford to silently drop a node because one attribute
        wasn't set yet. Fields fall through to whatever was last saved.
        """
        try: self.data.x = self.pos().x()
        except (RuntimeError, AttributeError): pass
        try: self.data.y = self.pos().y()
        except (RuntimeError, AttributeError): pass
        try: self.data.width = self.rect().width()
        except (RuntimeError, AttributeError): pass
        try: self.data.height = self.rect().height()
        except (RuntimeError, AttributeError): pass
        try: self.data.z_value = self.zValue()
        except (RuntimeError, AttributeError): pass
        self.data.ports_visible = getattr(self, 'ports_visible', self.data.ports_visible)
        self.data.shelf_visible = getattr(self, '_buttons_visible', self.data.shelf_visible)

    def to_dict(self) -> dict:
        """Sync visual state into data, then serialize."""
        self.sync_data()
        return self.data.to_dict()

