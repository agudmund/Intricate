#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/NodeData.py NodeData data class
-The identity and state of a node. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import uuid as _uuid
from dataclasses import dataclass, field


@dataclass
class NodeData:
    """
    The script and identity of a node. No Qt. No rendering. No opinions about
    how it looks or where it lives on screen.

    This is what a node IS. BaseNode is what a node LOOKS LIKE.

    Every piece of state that needs to survive a session save or travel between
    systems lives here. Everything visual lives in BaseNode and reads from here.

    Subclasses extend this with type-specific fields — a WarmNode adds body_text,
    an ImageNode adds image_b64, a HealthNode adds nothing because its state is
    always live. The base fields below are universal to every node type.

    Serialization:
        to_dict() and from_dict() live here, not on the graphics item.
        BaseNode never touches JSON. NodeData never touches QPainter.
        These two things have never met and never will.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    node_id:  int   = 0
    node_type: str  = "node"
    title:    str   = "Node"
    uuid:     str   = field(default_factory=lambda: _uuid.uuid4().hex)

    # ── Geometry ──────────────────────────────────────────────────────────────
    # Position and size are stored here so session restore doesn't need
    # to reach into the graphics item.
    x:      float = 0.0
    y:      float = 0.0
    width:  float = 300.0
    height: float = 200.0

    # ── Port state ────────────────────────────────────────────────────────────
    # Persisted so wiring mode survives session save/load.
    ports_visible: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Serialize to a plain dictionary for session persistence.

        Subclasses call super().to_dict() and extend the result with their
        own fields. The base dict is the guaranteed minimum every node type
        produces. Nothing here knows about JSON, files, or Qt.
        """
        return {
            "node_id":       self.node_id,
            "node_type":     self.node_type,
            "title":         self.title,
            "uuid":          self.uuid,
            "x":             self.x,
            "y":             self.y,
            "width":         self.width,
            "height":        self.height,
            "ports_visible": self.ports_visible,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NodeData':
        """
        Restore a NodeData from a session dictionary.

        Subclasses override this to restore their own fields, calling
        super().from_dict(data) to get the base instance first.
        """
        return cls(
            node_id       = data.get("node_id",       0),
            node_type     = data.get("node_type",     "node"),
            title         = data.get("title",         "Node"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   300.0)),
            height        = float(data.get("height",  200.0)),
            ports_visible = data.get("ports_visible", False),
        )
