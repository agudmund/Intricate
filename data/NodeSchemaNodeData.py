#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/NodeSchemaNodeData.py node schema data
-Dataclass for the Node Type Schema.md renderer node for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.MarkdownNodeData import MarkdownNodeData


@dataclass
class NodeSchemaNodeData(MarkdownNodeData):
    node_type: str   = field(default="node_schema")
    title:     str   = field(default="Node Schema")
    width:     float = field(default=520.0)
    height:    float = field(default=460.0)

    @classmethod
    def from_dict(cls, data: dict) -> 'NodeSchemaNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Node Schema"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   520.0)),
            height        = float(data.get("height",  460.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
        )
