#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/WormholeNodeData.py WormholeNodeData data class
-Identity and state for the WormholeNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class WormholeNodeData(NodeData):
    """
    The identity of a WormholeNode.

    Stores the last export status message so it survives session save/load.
    source_paths are not persisted — they are collected live from connected nodes
    at export time.
    """

    node_type:       str   = field(default="wormhole")
    title:           str   = field(default="Wormhole")
    width:           float = field(default=280.0)
    height:          float = field(default=200.0)
    last_status:     str   = field(default="")    # Last export status text
    last_export_dir: str   = field(default="")    # Folder of last written .prproj

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["last_status"]     = self.last_status
        data["last_export_dir"] = self.last_export_dir
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'WormholeNodeData':
        import uuid as _uuid
        return cls(
            node_id         = data.get("node_id",         0),
            title           = data.get("title",           "Wormhole"),
            uuid            = data.get("uuid",            _uuid.uuid4().hex),
            x               = float(data.get("x",         0.0)),
            y               = float(data.get("y",         0.0)),
            width           = float(data.get("width",     280.0)),
            height          = float(data.get("height",    200.0)),
            ports_visible   = data.get("ports_visible",   False),
            shelf_visible   = data.get("shelf_visible",   True),
            last_status     = data.get("last_status",     ""),
            last_export_dir = data.get("last_export_dir", ""),
        )
