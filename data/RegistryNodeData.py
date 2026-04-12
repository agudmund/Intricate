#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/RegistryNodeData.py registry data
-Dataclass for the node registry viewer for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.MarkdownNodeData import MarkdownNodeData


@dataclass
class RegistryNodeData(MarkdownNodeData):
    node_type: str   = field(default="registry")
    title:     str   = field(default="Registry")
    width:     float = field(default=560.0)
    height:    float = field(default=500.0)

    @classmethod
    def from_dict(cls, data: dict) -> 'RegistryNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Registry"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   560.0)),
            height        = float(data.get("height",  500.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            label         = data.get("label",         ""),
            depth_front   = data.get("depth_front",   False),
        )
