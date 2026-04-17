#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/PremiereBridgeNodeData.py Premiere bridge data class
-The identity and target address of a PremiereBridgeNode, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class PremiereBridgeNodeData(NodeData):
    """State for a PremiereBridgeNode.

    Persists only the wire target (host/port) and the Premiere clip
    address (track/clip indices). Connection status is runtime-only —
    it re-establishes itself on load.

    Phase 2+ may add: handshake state cache, last known FPS, expected
    project/sequence names for validation.
    """

    node_type: str   = field(default="premiere_bridge")
    title:     str   = field(default="Premiere Bridge")
    width:     float = field(default=340.0)
    height:    float = field(default=180.0)

    # Transport target — WebSocket now, swappable for Serial in Phase 2b.
    host: str = field(default="127.0.0.1")
    port: int = field(default=9914)

    # Premiere clip address — which timeline cell packets target.
    target_track: int = field(default=0)
    target_clip:  int = field(default=0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["host"]         = self.host
        data["port"]         = self.port
        data["target_track"] = self.target_track
        data["target_clip"]  = self.target_clip
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'PremiereBridgeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Premiere Bridge"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   340.0)),
            height        = float(data.get("height",  180.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            host          = str(data.get("host", "127.0.0.1")),
            port          = int(data.get("port", 9914)),
            target_track  = int(data.get("target_track", 0)),
            target_clip   = int(data.get("target_clip",  0)),
        )
