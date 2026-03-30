#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ClaudeNodeData.py ClaudeNodeData data class
-Identity and state for the ClaudeNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass(slots=True)
class ClaudeNodeData(NodeData):
    """
    The identity of a ClaudeNode.

    Skeletal data class — ready for type-specific fields to be added.
    Inherits all base geometry, identity, and port state from NodeData.
    """

    node_type:   str   = field(default="claude")
    title:       str   = field(default="Claude Node")
    width:       float = field(default=300.0)
    height:      float = field(default=200.0)
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ClaudeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Claude Node"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   300.0)),
            height        = float(data.get("height",  200.0)),
            ports_visible = data.get("ports_visible", False),
            depth_front   = data.get("depth_front",   False),
        )
