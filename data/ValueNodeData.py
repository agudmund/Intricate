#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ValueNodeData.py ValueNodeData data class
-State for the transparent value sequence node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class ValueNodeData(NodeData):
    node_type:     str   = field(default="value")
    title:         str   = field(default="Value")
    width:         float = field(default=220.0)
    height:        float = field(default=200.0)
    current_frame: int   = field(default=0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["current_frame"] = self.current_frame
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ValueNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Value"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   220.0)),
            height        = float(data.get("height",  200.0)),
            ports_visible = data.get("ports_visible", False),
            current_frame = int(data.get("current_frame", 0)),
        )
