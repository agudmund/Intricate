#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/LogNodeData.py LogNodeData data class
-State for the live log tail node — position and size only, content is always read from file for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class LogNodeData(NodeData):
    node_type:   str   = field(default="log")
    title:       str   = field(default="intricate.log")
    width:       float = field(default=440.0)
    height:      float = field(default=320.0)
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'LogNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "intricate.log"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   440.0)),
            height        = float(data.get("height",  320.0)),
            ports_visible = data.get("ports_visible", False),
            depth_front   = data.get("depth_front",   False),
        )
