#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ArchitectureNodeData.py architecture data
-Dataclass for the Architecture.md renderer node for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.MarkdownNodeData import MarkdownNodeData


@dataclass
class ArchitectureNodeData(MarkdownNodeData):
    node_type: str   = field(default="architecture")
    title:     str   = field(default="Architecture")
    width:     float = field(default=520.0)
    height:    float = field(default=460.0)

    @classmethod
    def from_dict(cls, data: dict) -> 'ArchitectureNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Architecture"),
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
