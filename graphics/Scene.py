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
        return node

    def add_warm_node(self, pos: QPointF | None = None):
        """Add a WarmNode at pos."""
        from nodes.WarmNode import WarmNode
        node = WarmNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        return node

    def add_about_node(self, pos: QPointF | None = None):
        """Add an AboutNode at pos."""
        from nodes.AboutNode import AboutNode
        node = AboutNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        return node

    def add_claude_node(self, pos: QPointF | None = None):
        """Add a ClaudeNode at pos."""
        from nodes.ClaudeNode import ClaudeNode
        node = ClaudeNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        return node

    def add_bezier_node(self, pos: QPointF | None = None):
        """Add a BezierNode at pos."""
        from nodes.BezierNode import BezierNode
        node = BezierNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
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

        if path:
            node.load_from_path(path)

        return node
