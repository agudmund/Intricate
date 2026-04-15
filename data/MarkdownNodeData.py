#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/MarkdownNodeData.py markdown base data
-Base dataclass for all markdown-rendering node types for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class MarkdownNodeData(NodeData):
    node_type:   str   = field(default="markdown")
    title:       str   = field(default="Markdown")
    width:       float = field(default=720.0)
    height:      float = field(default=400.0)
    label:       str   = field(default="")
    depth_front: bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"]       = self.label
        data["depth_front"] = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'MarkdownNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Markdown"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   720.0)),
            height        = float(data.get("height",  400.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
        )
