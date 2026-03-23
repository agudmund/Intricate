#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/HealthNodeData.py
-Identity and state for the HealthNode. Pure Python, zero Qt.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from .NodeData import NodeData
from .Theme import Theme


@dataclass(slots=True)
class HealthNodeData(NodeData):
    """
    The identity of a HealthNode.

    Health readings (_living_nodes, _scene_nodes, etc.) are deliberately
    excluded from serialization — they are always live, never restored.
    A HealthNode restarts as a fresh monitor on every session load.
    Stale diagnostic readings from a previous session have no meaning
    in a new one.

    Only structural identity travels through sessions: position, size,
    port state — the same minimum every node type carries.
    """

    node_type: str  = field(default="health")
    title:     str  = field(default="Health")
    width:     float = field(default_factory=lambda: Theme.healthNodeWidth)
    height:    float = field(default_factory=lambda: Theme.healthNodeHeight)

    def to_dict(self) -> dict:
        """Structural identity only — readings are always live."""
        return super().to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> 'HealthNodeData':
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Health"),
            uuid          = data.get("uuid",          __import__('uuid').uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   Theme.healthNodeWidth)),
            height        = float(data.get("height",  Theme.healthNodeHeight)),
            ports_visible = data.get("ports_visible", False),
        )
