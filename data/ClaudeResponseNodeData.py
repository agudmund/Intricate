#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ClaudeResponseNodeData.py ClaudeResponseNodeData class
-State for a multiline Claude reply sticky node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class ClaudeResponseNodeData(NodeData):
    node_type:   str   = field(default="claude_response")
    title:       str   = field(default="Response")
    width:       float = field(default=0.0)
    height:      float = field(default=0.0)
    label:       str   = field(default="")
    emoji:       str   = field(default="")
    depth_front: bool  = field(default=False)
    node_tint:   str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"]       = self.label
        data["depth_front"] = self.depth_front
        data["node_tint"]   = self.node_tint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ClaudeResponseNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Response"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   0.0)),
            height        = float(data.get("height",  0.0)),
            ports_visible = data.get("ports_visible", False),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
            node_tint     = data.get("node_tint", data.get("accent_color", "")),
        )
