#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Scene.py IntricateScene class
-The infinite canvas. Holds items, manages the world, owns the purge contract for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import QPointF


class IntricateScene(QGraphicsScene):
    """
    The world.

    All nodes enter the scene through creation methods here.
    The scene enforces constraints (one HealthNode, spawn position logic)
    and will own the purge contract and node registry when sessions arrive.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Tight focal area for the experimental phase.
        # Cat strategy: certain ground first, expand when ready.
        self.setSceneRect(-500.0, -500.0, 1000.0, 1000.0)

        self._floating_conn = None   # Connection being drawn, None when idle

        # Monotonic counters — incremented each time a node is raised.
        # Keeps same-tier nodes ordered by recency without crossing z-tiers.
        self._back_z_top  = -10.0
        self._front_z_top =  10.0

    def raise_node(self, node) -> None:
        """Bring node to the top of its z-tier (back or front)."""
        is_front = getattr(node.data, 'depth_front', False)
        if is_front:
            self._front_z_top += 0.001
            node.setZValue(self._front_z_top)
        else:
            self._back_z_top += 0.001
            node.setZValue(self._back_z_top)

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTION WIRING
    # ─────────────────────────────────────────────────────────────────────────

    def begin_connection(self, start_node) -> None:
        """Start drawing a wire from start_node's output port."""
        from graphics.Connection import Connection
        if self._floating_conn:
            self.cancel_connection()
        conn = Connection(start_node)
        self._floating_conn = conn
        self.addItem(conn)

    def update_floating_connection(self, scene_pos: QPointF) -> None:
        """Track the mouse position while a wire is being drawn."""
        if self._floating_conn:
            self._floating_conn.update_path(scene_pos)

    def complete_connection(self, end_node, explicit_port=None) -> None:
        """Snap the floating wire to end_node's input port."""
        if not self._floating_conn:
            return
        conn = self._floating_conn
        self._floating_conn = None
        if conn.start_node is end_node:
            self._discard_connection(conn)
            return
        conn.end_node = end_node
        if explicit_port is not None:
            conn.end_input_port = explicit_port
        # Corner routing is now fully dynamic in Connection.update_path —
        # end_input_port is retained only for explicit overrides (e.g. clicking a specific port).
        end_node.connections.append(conn)
        conn.update_path()

    def cancel_connection(self) -> None:
        """Discard the floating wire without completing it."""
        if self._floating_conn:
            self._discard_connection(self._floating_conn)
            self._floating_conn = None

    def _discard_connection(self, conn) -> None:
        try:
            conn.start_node.connections.remove(conn)
        except ValueError:
            pass
        self.removeItem(conn)

    # ─────────────────────────────────────────────────────────────────────────
    # NODE CREATION
    # ─────────────────────────────────────────────────────────────────────────

    def add_health_node(self, pos: QPointF | None = None):
        """
        Add a HealthNode at pos. One per scene — returns existing if present.
        """
        from nodes.HealthNode import HealthNode

        for item in self.items():
            if isinstance(item, HealthNode):
                return item

        node = HealthNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_warm_node(self, pos: QPointF | None = None):
        """Add a WarmNode at pos."""
        from nodes.WarmNode import WarmNode
        node = WarmNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_about_node(self, pos: QPointF | None = None, label: str | None = None):
        """Add an AboutNode at pos."""
        from nodes.AboutNode import AboutNode
        from data.AboutNodeData import AboutNodeData
        data = AboutNodeData(label=label) if label is not None else AboutNodeData()
        node = AboutNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_claude_response_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a ClaudeResponseNode (multiline reply sticky) at pos."""
        from nodes.ClaudeResponseNode import ClaudeResponseNode
        from data.ClaudeResponseNodeData import ClaudeResponseNodeData
        from PySide6.QtCore import QPointF
        node = ClaudeResponseNode(ClaudeResponseNodeData(label=label))
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_claude_node(self, pos: QPointF | None = None):
        """Add a ClaudeNode at pos."""
        from nodes.ClaudeNode import ClaudeNode
        node = ClaudeNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_text_node(self, pos: QPointF | None = None):
        """Add a TextNode at pos."""
        from nodes.TextNode import TextNode
        node = TextNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_bezier_node(self, pos: QPointF | None = None):
        """Add a BezierNode at pos."""
        from nodes.BezierNode import BezierNode
        node = BezierNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_image_node(self, pos: QPointF | None = None, path: str | None = None):
        """
        Add an ImageNode at pos, optionally loading an image from path.

        Called by the Node button (no path, opens file browser on double-click)
        and by View.dropEvent (path provided directly from the dropped file).
        """
        from nodes.ImageNode import ImageNode

        node = ImageNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)

        if path:
            node.load_from_path(path)

        return node
