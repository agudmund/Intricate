#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/SessionNodeData.py SessionNodeData data class
-Identity and state for the SessionNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class SessionNodeData(NodeData):
    """
    The identity of a SessionNode.

    Holds a reference to a session .json file and a cached summary of its
    contents — node count, type breakdown — so paint_content can render
    without re-parsing the file every frame.
    """

    node_type: str   = field(default="session")
    title:     str   = field(default="Session")
    width:     float = field(default=280.0)
    height:    float = field(default=260.0)

    source_path:      str  = field(default="")     # Absolute path to the dropped .json file
    session_name:     str  = field(default="")     # Filename stem for display
    description:      str  = field(default="")     # One-liner from session metadata (written by ClaudeNode)
    node_count:       int  = field(default=0)      # Number of nodes in the session
    connection_count: int  = field(default=0)      # Number of connections
    type_breakdown:   str  = field(default="")     # Pre-formatted e.g. "3 warm, 2 image, 1 bezier"
    imported:         bool = field(default=False)  # True after the import button has been pressed

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["source_path"]      = self.source_path
        data["session_name"]     = self.session_name
        data["description"]      = self.description
        data["node_count"]       = self.node_count
        data["connection_count"] = self.connection_count
        data["type_breakdown"]   = self.type_breakdown
        data["imported"]         = self.imported
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionNodeData':
        import uuid as _uuid
        return cls(
            node_id          = data.get("node_id",          0),
            title            = data.get("title",            "Session"),
            uuid             = data.get("uuid",             _uuid.uuid4().hex),
            x                = float(data.get("x",          0.0)),
            y                = float(data.get("y",          0.0)),
            width            = float(data.get("width",      280.0)),
            height           = float(data.get("height",     260.0)),
            ports_visible    = data.get("ports_visible",    False),
            shelf_visible    = data.get("shelf_visible",    True),
            source_path      = data.get("source_path",      ""),
            session_name     = data.get("session_name",     ""),
            description      = data.get("description",      ""),
            node_count       = data.get("node_count",       0),
            connection_count = data.get("connection_count",  0),
            type_breakdown   = data.get("type_breakdown",   ""),
            imported         = data.get("imported",         False),
        )
