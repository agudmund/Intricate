#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/Port.py Port class
-A connection point. Knows its owner and its role. Nothing more for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QPen, QColor

from pretty_widgets.graphics.Theme import Theme


# Port visual constants — resolved from Theme at import time
_RADIUS      = 8                            # Hit area and visual size
_COLOR_IN    = QColor("#7a9e8a")            # Input — cool mint
_COLOR_OUT   = QColor("#a07a5a")            # Output — warm amber
_COLOR_HOVER = QColor("#d2d1cf")            # Either port on hover
_BORDER      = QColor(Theme.primaryBorder)
_BORDER_W    = 1.0
_GLOW_BLUR   = 12
_GLOW_COLOR  = QColor(Theme.primaryBorder)


class Port(QGraphicsEllipseItem):
    """
    A connection point. First-class citizen of Intricate.

    A port knows three things:
        - Who owns it (parent_node)
        - Whether it is an output or input (is_output)
        - Whether it is currently connected (connected)

    What flows through it, and what that data means, is not the port's
    concern. That belongs to the wire and eventually the graph engine.

    Visual behaviour:
        Hidden by default — shown only when the scene's wiring mode is active.
        Output ports are the drag origin for drawing new connections.
        Input ports are the drop target.
        Both highlight on hover so the user knows they are clickable.

    Structural position:
        Ports are child items of their parent node so they inherit scene
        position changes automatically. _place_ports() on BaseNode controls
        where they sit relative to the node body.
    """

    def __init__(self, parent_node, *, is_output: bool):
        # Diameter = 2 * radius, centered on the port's local origin
        d = _RADIUS * 2
        super().__init__(-_RADIUS, -_RADIUS, d, d, parent_node)

        self.parent_node = parent_node
        self.is_output   = is_output
        self.connected   = False

        self._configure()

    def _configure(self) -> None:
        base_color = _COLOR_OUT if self.is_output else _COLOR_IN
        self.setBrush(QBrush(base_color))
        self.setPen(QPen(_BORDER, _BORDER_W))

        # Ports don't move independently — the node moves, ports follow
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(_GLOW_BLUR)
        glow.setColor(_GLOW_COLOR)
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    # ─────────────────────────────────────────────────────────────────────────
    # HOVER
    # ─────────────────────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(QBrush(_COLOR_HOVER))
        self.setCursor(Qt.CrossCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        base_color = _COLOR_OUT if self.is_output else _COLOR_IN
        self.setBrush(QBrush(base_color))
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self.is_output:
                self.parent_node.on_port_clicked(self, event)
                event.accept()
                return
            else:
                # Input port — complete a floating connection if one is in progress
                scene = self.scene()
                if scene and hasattr(scene, '_floating_conn') and scene._floating_conn:
                    scene.complete_connection(self.parent_node, explicit_port=self)
                    event.accept()
                    return
        super().mousePressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # STATE
    # ─────────────────────────────────────────────────────────────────────────

    def set_connected(self, connected: bool) -> None:
        """
        Mark this port as connected or free.
        Visual feedback can be added here when the design calls for it.
        """
        self.connected = connected
        self.update()
