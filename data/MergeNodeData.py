#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/MergeNodeData.py MergeNodeData data class
-Identity and state for the MergeNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class MergeNodeData(NodeData):
    """
    The identity of a MergeNode.

    Lists connected AudioNodes in sequential order.
    A staging area for audio merge operations.
    """

    node_type:   str   = field(default="merge")
    title:       str   = field(default="Merge")
    width:       float = field(default=260.0)
    height:      float = field(default=200.0)

    depth_front: bool  = field(default=False)
    node_tint:   str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["depth_front"] = self.depth_front
        data["node_tint"]   = self.node_tint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'MergeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",      0),
            title         = data.get("title",        "Merge"),
            uuid          = data.get("uuid",         _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  260.0)),
            height        = float(data.get("height", 200.0)),
            ports_visible = data.get("ports_visible", True),
            shelf_visible = data.get("shelf_visible", True),
            emoji         = data.get("emoji",        ""),
            depth_front   = data.get("depth_front",  False),
            node_tint     = data.get("node_tint",    ""),
        )
