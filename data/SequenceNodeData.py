#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/SequenceNodeData.py SequenceNodeData data class
-Identity and state for the SequenceNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class SequenceNodeData(NodeData):
    """
    The identity of a SequenceNode.

    folder_path points to a directory of image files on disk.
    current_frame is the slider position (0-based index).
    No base64 — frames are loaded from disk on demand.
    """

    node_type:     str   = field(default="sequence")
    title:         str   = field(default="Sequence")
    width:         float = field(default=320.0)
    height:        float = field(default=300.0)
    folder_path:   str   = field(default="")
    current_frame: int   = field(default=0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["folder_path"]   = self.folder_path
        data["current_frame"] = self.current_frame
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'SequenceNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "Sequence"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   320.0)),
            height        = float(data.get("height",  300.0)),
            ports_visible = data.get("ports_visible", False),
            folder_path   = data.get("folder_path",   ""),
            current_frame = int(data.get("current_frame", 0)),
        )
