#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/NullNodeData.py NullNodeData data class
-State for a transparent passthrough anchor node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class NullNodeData(NodeData):
    node_type:   str   = field(default="null")
    title:       str   = field(default="Null")
    width:       float = field(default=80.0)
    height:      float = field(default=80.0)
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'NullNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Null"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   80.0)),
            height        = float(data.get("height",  80.0)),
            ports_visible = data.get("ports_visible", True),
            depth_front   = data.get("depth_front",   False),
        )
