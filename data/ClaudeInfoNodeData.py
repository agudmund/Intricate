#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ClaudeInfoNodeData.py ClaudeInfoNodeData data class
-Identity and state for the ClaudeInfoNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class ClaudeInfoNodeData(NodeData):
    """
    Identity of a ClaudeInfoNode — the live token-usage dashboard.

    All readings are live-polled from JSONL files; nothing numeric is
    serialized.  Only structural identity travels through sessions.
    """

    node_type:   str   = field(default="claude_info")
    title:       str   = field(default="Claude Info")
    width:       float = field(default=280.0)
    height:      float = field(default=320.0)
    folder_path: str   = field(default="")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["folder_path"] = self.folder_path
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'ClaudeInfoNodeData':
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Claude Info"),
            uuid          = data.get("uuid",          __import__('uuid').uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   280.0)),
            height        = float(data.get("height",  320.0)),
            ports_visible = data.get("ports_visible", False),
            folder_path   = data.get("folder_path",   ""),
        )
