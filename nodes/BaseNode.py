#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/BaseNode.py BaseNode class
-The visual and structural foundation every node type builds on, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time as _time
import uuid as _uuid
from PySide6.QtWidgets import QGraphicsRectItem
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QFont
from PySide6.QtWidgets import QGraphicsItem

from data.NodeData import NodeData
from nodes.NodeBehaviour import NodeBehaviour
from pretty_widgets.graphics.Theme import Theme
from nodes.NodeButton import NodeButton, EmojiButton, BUTTON_SIZE


def _c(hex_str): return QColor(hex_str)   # local shorthand

# Shake-to-delete cooldown — module-level, shared across all nodes.
# Prevents cascade-deletes when Qt transfers the mouse grab after removal.
_SHAKE_COOLDOWN_S       = 0.8
_shake_cooldown_until: float = 0.0


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
            import random
            from utils.IconPicker import emojiIcons
            data.emoji = random.choice(emojiIcons)
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
            from utils.ColorPicker import all_colors as _ac
            try:
                self._color_index = _ac().index(_saved_tint)
            except ValueError:
                self._color_index = 0

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
        self._anim_top_offset = self._BUTTON_ZONE_H if self._buttons_visible else 8.0

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
        before they reach the child.  Without this, the QTextEdit proxy eats
        the right-click for its context menu and BaseNode never sees it."""
        from PySide6.QtCore import QEvent
        if (event.type() == QEvent.GraphicsSceneMousePress
                and event.button() == Qt.RightButton):
            self.mousePressEvent(event)
            return True   # handled — child does not see it
        return super().sceneEventFilter(watched, event)

    def itemChange(self, change, value):
        if (change == QGraphicsRectItem.GraphicsItemChange.ItemSceneChange
                and value is None):
            self._prepare_for_removal()

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

    def _prepare_for_removal(self):
        """
        Graceful exit — called when this node is leaving its scene.

        Order matters:
            1. Heal wires — bridge sources to targets before severing anything
            2. Disconnect Qt signals (behaviour) — before any Qt object is invalid
            3. Sever wire connections — while scene APIs are still valid
            4. Clear connection list — last, after all severing is done

        Do NOT set self.behaviour = None here. The finished signal on pulse_anim
        fires re-entrantly during teardown and will segfault if behaviour is gone.
        disconnect_all() severs the connections instead — that's sufficient.
        """
        self._heal_connections()
        self._detach_buttons()

        if hasattr(self, 'behaviour') and self.behaviour:
            self.behaviour.disconnect_all()

        for conn in list(self.connections):
            # Stop the glide animation before touching any node references
            if hasattr(conn, '_glide_timer'):
                conn._glide_timer.stop()
            # Remove from the other endpoint's connection list so it doesn't
            # hold a stale reference after this node is gone
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other is not None and other is not self and hasattr(other, 'connections'):
                try:
                    other.connections.remove(conn)
                except ValueError:
                    pass
            if conn.scene():
                conn.scene().removeItem(conn)
            conn.start_node = None
            conn.end_node   = None
        self.connections.clear()

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
        Pressing through all colors returns to the natural default."""
        from utils.ColorPicker import get as _pick, all_colors as _ac
        from PySide6.QtGui import QBrush
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
        scene = self.scene()

        if event.button() == Qt.RightButton:
            if scene and hasattr(scene, 'begin_connection'):
                scene.begin_connection(self)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            # Resize handle — bottom-right corner
            rect = self.rect()
            handle = QRectF(rect.right() - _RESIZE_GRIP,
                            rect.bottom() - _RESIZE_GRIP,
                            _RESIZE_GRIP, _RESIZE_GRIP)
            if handle.contains(event.pos()):
                self._is_resizing      = True
                self._resize_start_pos  = event.pos()
                self._resize_start_rect = self.rect()
                event.accept()
                return
        self._is_resizing = False
        self._shake_samples.clear()
        self._shake_triggered = False
        self._shake_press_active = True
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

    def _track_shake(self) -> None:
        """Sample position during drag at ~30ms intervals and check for shake.

        Gated on _shake_press_active so stray move events after another node's
        removal can't trigger shake without a proper press first.
        Also gated on a module-level cooldown that blocks cascade-deletes when
        Qt transfers the mouse grab after the previous node was removed.
        """
        global _shake_cooldown_until
        if _time.monotonic() < _shake_cooldown_until:
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
        Shake while unconnected → dissolve the node with a particle burst."""
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
        sprinkle(scene, self.mapToScene(self.rect().center()), count=3000)

        for src in sources:
            for tgt in targets:
                if src is tgt:
                    continue
                new_conn = Connection(src, tgt)
                scene.addItem(new_conn)
                new_conn.update_path()

    def _shake_delete(self) -> None:
        """Dissolve this node with a particle burst. Deferred to mouseRelease
        so the mouse grab releases cleanly before the scene removes the item."""
        global _shake_cooldown_until
        scene = self.scene()
        if not scene:
            return
        # Snapshot the node data before deletion so the sidebar can restore it.
        try:
            scene._last_deleted = self.to_dict()
        except Exception:
            pass
        _shake_cooldown_until = _time.monotonic() + _SHAKE_COOLDOWN_S
        from graphics.Particles import sprinkle
        sprinkle(scene, self.mapToScene(self.rect().center()), count=3000)
        self._pending_shake_delete = True

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        self._shake_press_active = False
        # Sync geometry back to data after a resize or move
        self.data.x      = self.pos().x()
        self.data.y      = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        super().mouseReleaseEvent(event)
        # Release the scene mouse grab only if THIS item still holds it.
        # ungrabMouse() is NOT a safe no-op on non-grabbers — it touches Qt's
        # internal dispatch state and can break selection on neighboring items
        # that received a transferred grab after a shake-delete.
        if not event.buttons():
            scene = self.scene()
            if scene and scene.mouseGrabberItem() is self:
                self.ungrabMouse()
        # Deferred shake-delete — item must already be ungrabbed before removal.
        if self._pending_shake_delete:
            self._pending_shake_delete = False
            scene = self.scene()
            if scene:
                def _deferred_remove(node=self, sc=scene):
                    # Last-moment grab release — Qt can re-establish grabs
                    # between mouseReleaseEvent and the deferred callback.
                    try:
                        if sc.mouseGrabberItem() is node:
                            node.ungrabMouse()
                    except RuntimeError:
                        pass
                    sc.removeItem(node)
                QTimer.singleShot(0, _deferred_remove)


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
            self._shelf_anim.setEndValue(8.0)
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
        """Extend bounding rect to include shadow margin so repaints are clean."""
        return self.rect().adjusted(
            -_SHADOW_MARGIN, -_SHADOW_MARGIN,
             _SHADOW_MARGIN,  _SHADOW_MARGIN
        )

    def shape(self):
        """Hit-test shape matches the visible node border, not the shadow margin."""
        path = QPainterPath()
        path.addRoundedRect(self.rect(), self.round_radius, self.round_radius)
        return path

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Selection pen overrides current pen
        pen = self.selected_pen if self.isSelected() else self.current_pen
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), self.round_radius, self.round_radius)

        # Hand off to subclass for type-specific content
        self.paint_content(painter)

        painter.restore()

    _BUTTON_ZONE_H   = 40.0   # px reserved for the button strip (4 pad + 32 button + 4 gap)
    _CONTENT_PAD     = 15.0   # horizontal padding for title/body text
    _TITLE_HEIGHT    = 40.0   # rect height allocated for title text
    _BODY_OFFSET     = 36.0   # px below title top where body text starts
    _TITLE_FONT      = "Chandler42"
    _TITLE_STYLE     = "MediumOblique"   # Chandler42's pretty variant
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
        top = self._content_top()
        return QRectF(
            r.left() + pad,
            r.top() + top,
            r.width() - pad * 2,
            r.height() - self._anim_top_offset,
        )

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
        """
        self.data.x             = self.pos().x()
        self.data.y             = self.pos().y()
        self.data.width         = self.rect().width()
        self.data.height        = self.rect().height()
        self.data.z_value       = self.zValue()
        self.data.ports_visible = self.ports_visible
        self.data.shelf_visible = self._buttons_visible

    def to_dict(self) -> dict:
        """Sync visual state into data, then serialize."""
        self.sync_data()
        return self.data.to_dict()

