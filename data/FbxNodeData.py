#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/FbxNodeData.py FbxNodeData data class
-Identity and state for the FbxNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class FbxNodeData(NodeData):
    """
    The identity of an FbxNode.

    A placeholder for the future FBX 3D model viewer node.
    Stores the path to an FBX file and will eventually hold
    camera parameters, render settings, and vertex data.
    """

    node_type:   str   = field(default="fbx")
    title:       str   = field(default="FBX")
    width:       float = field(default=280.0)
    height:      float = field(default=200.0)

    fbx_path:    str   = field(default="")
    depth_front: bool  = field(default=False)
    node_tint:   str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["fbx_path"]    = self.fbx_path
        data["depth_front"] = self.depth_front
        data["node_tint"]   = self.node_tint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'FbxNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",      0),
            title         = data.get("title",        "FBX"),
            uuid          = data.get("uuid",         _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  280.0)),
            height        = float(data.get("height", 200.0)),
            ports_visible = data.get("ports_visible", False),
            fbx_path      = data.get("fbx_path",    ""),
            depth_front   = data.get("depth_front",  False),
            node_tint     = data.get("node_tint",    ""),
        )
