#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ReadmeNodeData.py ReadmeNodeData data class
-State for a markdown-rendering read-only node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class ReadmeNodeData(NodeData):
    node_type:   str   = field(default="readme")
    title:       str   = field(default="Readme")
    width:       float = field(default=400.0)
    height:      float = field(default=320.0)
    label:       str   = field(default="")
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"]       = self.label
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ReadmeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Readme"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   400.0)),
            height        = float(data.get("height",  320.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
        )
