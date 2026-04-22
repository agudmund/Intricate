#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/ValueNodeData.py ValueNodeData data class
-State for the chromeless transparent value-sequence node for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
import uuid as _uuid

from data.ChromelessRootData import ChromelessRootData


@dataclass
class ValueNodeData(ChromelessRootData):
    """State for the ValueNode — transparent image-sequence display
    with a scrubber slider, wired into the node graph via input/output
    ports. Rooted on ChromelessRootData so the viewport-pin trio
    (``pinned``, ``pin_vp_x``, ``pin_vp_y``) is inherited; to_dict
    chains cleanly through super().
    """

    node_type:     str   = field(default="value")
    title:         str   = field(default="Value")
    width:         float = field(default=130.0)
    height:        float = field(default=80.0)
    current_frame: int   = field(default=0)

    def to_dict(self) -> dict:
        data = super().to_dict()   # includes pin fields from ChromelessRootData
        data["current_frame"] = self.current_frame
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ValueNodeData':
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Value"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   130.0)),
            height        = float(data.get("height",  80.0)),
            z_value       = float(data.get("z_value",   0.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            # ChromelessRootData pin fields
            pinned        = bool(data.get("pinned",   False)),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
            # ValueNode-specific
            current_frame = int(data.get("current_frame", 0)),
        )
