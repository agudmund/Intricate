#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/TextNodeData.py TextNodeData data class
-State for a simple always-editable Lato text node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass(slots=True)
class TextNodeData(NodeData):
    node_type:   str   = field(default="text")
    title:       str   = field(default="Text")
    width:       float = field(default=240.0)
    height:      float = field(default=180.0)
    label:       str   = field(default="")
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"]       = self.label
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'TextNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Text"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   240.0)),
            height        = float(data.get("height",  180.0)),
            ports_visible = data.get("ports_visible", False),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
        )
