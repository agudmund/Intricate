#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/GitNodeData.py GitNodeData data class
-Identity and state for the GitNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class GitNodeData(NodeData):
    """
    The identity of a GitNode.

    A read-only dashboard showing all Desktop project repos
    with dirty/clean status indicators.
    """

    node_type:   str   = field(default="git")
    title:       str   = field(default="Git Status")
    width:       float = field(default=300.0)
    height:      float = field(default=400.0)
    depth_front: bool  = field(default=False)
    node_tint:   str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["depth_front"] = self.depth_front
        data["node_tint"]   = self.node_tint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'GitNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",      0),
            title         = data.get("title",        "Git Status"),
            uuid          = data.get("uuid",         _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  300.0)),
            height        = float(data.get("height", 400.0)),
            ports_visible = data.get("ports_visible", False),
            depth_front   = data.get("depth_front",  False),
            node_tint     = data.get("node_tint",    ""),
        )
