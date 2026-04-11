#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/CodeNodeData.py CodeNodeData data class
-State for a syntax-highlighted code display node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class CodeNodeData(NodeData):
    node_type:   str   = field(default="code")
    title:       str   = field(default="Code")
    width:       float = field(default=360.0)
    height:      float = field(default=280.0)
    label:       str   = field(default="")
    source_path: str   = field(default="")
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"]       = self.label
        data["source_path"] = self.source_path
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'CodeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Code"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   360.0)),
            height        = float(data.get("height",  280.0)),
            ports_visible = data.get("ports_visible", False),
            label         = data.get("label",         ""),
            source_path   = data.get("source_path",   ""),
            depth_front   = data.get("depth_front",   False),
        )
