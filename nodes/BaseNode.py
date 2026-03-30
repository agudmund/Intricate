#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/BaseNode.py BaseNode class
-The visual and structural foundation every node type builds on, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import uuid as _uuid
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QFont

from data.NodeData import NodeData
from nodes.NodeBehaviour import NodeBehaviour
from graphics.Theme import Theme
from nodes.NodeButton import NodeButton, BUTTON_SIZE


def _c(hex_str): return QColor(hex_str)   # local shorthand


# Visual constants resolved from Theme at import time
_BG              = _c(Theme.nodeBg)
_BORDER          = _c(Theme.nodeBorder)
_BORDER_SELECTED = _c(Theme.nodeBorderSelected)
_BORDER_WIDTH    = Theme.nodeBorderWidth
_BORDER_SELECTED_SCALE = Theme.nodeBorderSelectedScale
_ROUND_RADIUS    = Theme.nodeRoundRadius
_SHADOW_BLUR     = Theme.nodeShadowBlur
_SHADOW_COLOR    = _c(Theme.nodeShadowColor)
_SHADOW_OFFSET   = (Theme.nodeShadowOffsetX, Theme.nodeShadowOffsetY)
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
        self.data = data
        self.setPos(QPointF(data.x, data.y))

        # ── Connections ───────────────────────────────────────────────────────
        self.connections = []           # All Connection objects attached to this node
        self.temp_connection = None     # Active wire being drawn, cleared on release
        self.ports_visible = data.ports_visible

        # ── Ports ─────────────────────────────────────────────────────────────
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.input_port  = None
        self.output_port = None
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
        self.hover_pen     = QPen(_bc.lighter(130), _bw)
        self.selected_pen  = QPen(_bcs, _bw * _bss)
        self.current_pen   = self.normal_pen

        self.setBrush(QColor(Theme.nodeBg))
        self.setPen(self.current_pen)

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable      |
            QGraphicsRectItem.ItemIsSelectable   |
            QGraphicsRectItem.ItemSendsGeometryChanges |
            QGraphicsRectItem.ItemSendsScenePositionChanges
        )
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(self.rect().center())

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setColor(_SHADOW_COLOR)
        shadow.setOffset(*_SHADOW_OFFSET)
        self.setGraphicsEffect(shadow)

        # ── Button strip ──────────────────────────────────────────────────────
        # Built last — geometry must be final before positioning.
        # Subclasses append their own buttons by overriding _build_buttons().
        self._buttons: list[NodeButton] = []
        self._build_buttons()
        self._position_buttons()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if (change == QGraphicsRectItem.GraphicsItemChange.ItemSceneChange
                and value is None):
            self._prepare_for_removal()

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

    def _prepare_for_removal(self):
        """
        Graceful exit — called when this node is leaving its scene.

        Order matters:
            1. Disconnect Qt signals (behaviour) — before any Qt object is invalid
            2. Sever wire connections — while scene APIs are still valid
            3. Clear connection list — last, after all severing is done

        Do NOT set self.behaviour = None here. The finished signal on pulse_anim
        fires re-entrantly during teardown and will segfault if behaviour is gone.
        disconnect_all() severs the connections instead — that's sufficient.
        """
        self._detach_buttons()

        if hasattr(self, 'behaviour') and self.behaviour:
            self.behaviour.disconnect_all()

        for conn in list(self.connections):
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
            self._pending_update = False

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTON STRIP
    # ─────────────────────────────────────────────────────────────────────────

    _has_depth_toggle = False   # set to True in subclasses that want the front/back button

    def _build_buttons(self) -> None:
        """
        Construct the button strip. Base adds the universal delete button,
        and optionally a depth toggle if _has_depth_toggle is True.

        Subclasses that need additional buttons override and call super():
            def _build_buttons(self) -> None:
                super()._build_buttons()
                self._buttons.append(NodeButton(self, my_pix, self._my_action))

        Icons load from icons/ folder next to the package root.
        If files are missing, Theme.icon() returns a coloured circle fallback
        so the layout holds without requiring assets to be present first.
        """
        delete_pix         = Theme.icon(Theme.iconDelete,  fallback_color="#c97b7b")
        delete_confirm_pix = Theme.icon(Theme.iconConfirm, fallback_color="#d4a96a")
        self._buttons.append(
            NodeButton(self, delete_pix, self._delete_self, delete_confirm_pix)
        )
        if self._has_depth_toggle:
            depth_off_pix = Theme.icon(Theme.aboutDepthIconOff, fallback_color="#7b9bc9")
            depth_on_pix  = Theme.icon(Theme.aboutDepthIconOn,  fallback_color="#9bc97b")
            btn = NodeButton(self, depth_off_pix, self._depth_action, depth_on_pix, toggle=True)
            btn._in_confirm = getattr(self.data, 'depth_front', False)
            self._buttons.append(btn)

    def _depth_action(self) -> None:
        self.data.depth_front = not getattr(self.data, 'depth_front', False)
        self._apply_depth()

    def _apply_depth(self) -> None:
        self.setZValue(10.0 if getattr(self.data, 'depth_front', False) else -10.0)
        self.update()

    def _position_buttons(self) -> None:
        """
        Arrange buttons in a left-aligned row along the top of the node.
        Left alignment follows western reading-direction muscle memory —
        the eye and hand naturally reach top-left for quick actions.
        Called after _build_buttons() and again after any resize.
        """
        pad     = 4.0
        spacing = 4.0
        r       = self.rect()
        x       = r.left() + pad
        y       = r.top()  + pad

        for btn in self._buttons:
            btn.setPos(QPointF(x, y))
            x += BUTTON_SIZE + spacing

    def _detach_buttons(self) -> None:
        """Stop button timers before scene removal."""
        for btn in self._buttons:
            btn.detach()
        self._buttons.clear()

    def _delete_self(self) -> None:
        """Remove this node from the scene. Called by the delete button."""
        if self.scene():
            self.scene().removeItem(self)

    # ─────────────────────────────────────────────────────────────────────────
    # PORTS
    # ─────────────────────────────────────────────────────────────────────────

    def _create_ports(self):
        """Instantiate ports as child items, hidden until wiring mode is enabled."""
        # Port import is local to avoid circular imports at module load time
        from nodes.Port import Port
        self.input_port  = Port(self, is_output=False)
        self.output_port = Port(self, is_output=True)
        self._place_ports()
        self.input_port.hide()
        self.output_port.hide()

    def _place_ports(self):
        """Anchor ports to the vertical center of each side."""
        cy = self.rect().height() / 2
        self.input_port.setPos(-10, cy)
        self.output_port.setPos(self.rect().width() + 10, cy)

    def setRect(self, rect):
        """Keep ports anchored and wires live on resize."""
        super().setRect(rect)
        if self.input_port and self.output_port:
            self._place_ports()
        if hasattr(self, '_buttons'):
            self._position_buttons()
        for conn in self.connections:
            conn.update_path()

    def set_ports_visible(self, visible: bool) -> None:
        """Show or hide both ports. Called by the scene's wiring mode toggle."""
        self.ports_visible = visible
        if self.input_port:
            self.input_port.setVisible(visible)
        if self.output_port:
            self.output_port.setVisible(visible)

    def on_port_clicked(self, port, event) -> None:
        """
        Called by Port.mousePressEvent when an output port is clicked.

        Starts a temporary floating wire from this node's output port.
        The wire follows the mouse until released on a target input port,
        at which point the scene finalises the connection.

        Connection logic is a future concern — this stub exists so Port
        can call it without ImportError. It will be implemented when
        Connection.py arrives.
        """
        pass  # Connection wire drawing — implemented when Connection.py arrives

    # ─────────────────────────────────────────────────────────────────────────
    # MOUSE EVENTS
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
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

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        # Sync geometry back to data after a resize or move
        self.data.x      = self.pos().x()
        self.data.y      = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Override in subclasses for type-specific double-click behaviour."""
        super().mouseDoubleClickEvent(event)

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

    _BUTTON_ZONE_H = 24.0   # px reserved for the button strip (4 pad + 16 button + 4 gap)

    def paint_content(self, painter: QPainter):
        """
        Specialist paint handoff — override in subclasses.

        Called after the shell (background + border) is painted.
        Painter is in node-local coordinates.

        Default implementation draws self.data.title top-left using the
        node font and offset Theme values. Subclasses that need
        type-specific content override this entirely (no super() needed).
        """
        painter.save()
        r   = self.rect()
        pad = Theme.nodeTextPaddingLeft
        content_rect = QRectF(
            r.left()   + pad,
            r.top()    + self._BUTTON_ZONE_H + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop,
            r.width()  - pad,
            r.height() - self._BUTTON_ZONE_H,
        )
        painter.setPen(QColor(Theme.aboutFontColor))
        painter.setFont(QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize)))
        painter.drawText(content_rect, Qt.AlignLeft | Qt.AlignTop, self.data.title)
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
        self.data.ports_visible = self.ports_visible

    def to_dict(self) -> dict:
        """Sync visual state into data, then serialize."""
        self.sync_data()
        return self.data.to_dict()

