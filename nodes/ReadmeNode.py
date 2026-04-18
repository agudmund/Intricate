#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ReadmeNode.py ReadmeNode class
-Read-only markdown renderer with GitHub dark theme for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
import random

from PySide6.QtCore import QRectF, QPointF

from nodes.MarkdownNode import MarkdownNode
from data.ReadmeNodeData import ReadmeNodeData
from pretty_widgets.graphics.Theme import Theme


class ReadmeNode(MarkdownNode):
    """
    Read-only markdown rendering node with a spawn-nodes button.

    Inherits all markdown rendering from MarkdownNode. Adds the ability
    to split body text into individual AboutNodes via the button strip.
    """

    def __init__(self, data: ReadmeNodeData | None = None):
        if data is None:
            data = ReadmeNodeData()
        super().__init__(data)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        spawn_pix = Theme.icon(Theme.iconSpawnNodesClean, fallback_color="#7ab88a")
        btn = NodeButton(self, spawn_pix, self._split_into_about_nodes)
        btn._sticker_shadow = True
        self._buttons.append(btn)

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT — explode body text into individual AboutNodes
    # ─────────────────────────────────────────────────────────────────────────

    def _split_into_about_nodes(self) -> None:
        """Split each non-empty line of the body text into its own AboutNode."""
        scene = self.scene()
        if not scene:
            return

        text = self.data.label
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return

        from nodes.BaseNode import BaseNode as _BaseNode

        PADDING         = 28
        PROBES_PER_RING = 16
        _OFFSCREEN      = QPointF(-999_999, -999_999)

        origin = self.pos() + QPointF(self.rect().width() + 60, 0)

        for line in lines:
            node = scene.add_about_node(pos=_OFFSCREEN, label=line)
            node.data.title = line[:40]
            nr = node.rect()
            nw, nh = nr.width(), nr.height()

            step       = max(1, int(max(nw, nh)) // 2)
            max_radius = 4000

            def _clear(p):
                candidate = QRectF(p.x() - PADDING, p.y() - PADDING,
                                   nw + PADDING * 2, nh + PADDING * 2)
                for item in scene.items(candidate):
                    if item is node:
                        continue
                    # Duck-typed over BaseNode + StickerNode roots.
                    if hasattr(item, 'data') and hasattr(item, 'to_dict'):
                        return False
                return True

            pos = origin
            found = _clear(origin)
            if not found:
                for radius in range(step, max_radius, step):
                    base = random.uniform(0, 2 * math.pi)
                    for k in range(PROBES_PER_RING):
                        angle = base + k * (2 * math.pi / PROBES_PER_RING)
                        candidate = QPointF(
                            origin.x() + math.cos(angle) * radius,
                            origin.y() + math.sin(angle) * radius,
                        )
                        if _clear(candidate):
                            pos = candidate
                            found = True
                            break
                    if found:
                        break

            if not found:
                pos = origin

            node.setPos(pos)
            origin = pos + QPointF(nw + 40, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def from_dict(data: dict) -> 'ReadmeNode':
        return ReadmeNode(ReadmeNodeData.from_dict(data))
