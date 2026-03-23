#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/BezierNodeData.py
-Identity and state for the BezierNode. Pure Python, zero Qt.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from .NodeData import NodeData


@dataclass(slots=True)
class BezierNodeData(NodeData):
    """
    The identity of a BezierNode.

    Stores the two bezier control handle positions as offsets relative
    to the node's own coordinate space. Relative storage means the curve
    shape survives moves and resizes without needing recalculation.

    Four points define the cubic bezier:
        p0  — curve start  (left edge center, derived from geometry)
        cp1 — control point 1 (user-draggable handle, stored here)
        cp2 — control point 2 (user-draggable handle, stored here)
        p3  — curve end    (right edge center, derived from geometry)

    p0 and p3 are always derived from the node rect at paint time —
    only the two handle offsets need to be persisted.
    """

    node_type: str  = field(default="bezier")
    title:     str  = field(default="Curve")
    width:     float = field(default=300.0)
    height:    float = field(default=160.0)

    # Control handle positions as offsets from node center
    # Defaults place the handles in a gentle S-curve spread
    cp1_x: float = field(default=0.0)
    cp1_y: float = field(default=0.0)
    cp2_x: float = field(default=0.0)
    cp2_y: float = field(default=0.0)

    _handles_initialised: bool = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["cp1_x"] = self.cp1_x
        data["cp1_y"] = self.cp1_y
        data["cp2_x"] = self.cp2_x
        data["cp2_y"] = self.cp2_y
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'BezierNodeData':
        import uuid as _uuid
        return cls(
            node_id              = data.get("node_id",   0),
            title                = data.get("title",     "Curve"),
            uuid                 = data.get("uuid",      _uuid.uuid4().hex),
            x                    = float(data.get("x",       0.0)),
            y                    = float(data.get("y",       0.0)),
            width                = float(data.get("width",   300.0)),
            height               = float(data.get("height",  160.0)),
            ports_visible        = data.get("ports_visible", False),
            cp1_x                = float(data.get("cp1_x",   0.0)),
            cp1_y                = float(data.get("cp1_y",   0.0)),
            cp2_x                = float(data.get("cp2_x",   0.0)),
            cp2_y                = float(data.get("cp2_y",   0.0)),
            _handles_initialised = True,
        )
