#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/JoyStatsNodeData.py JoyStatsNode data class
-Identity and state for the live joy-tamagotchi HUD, chromeless for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
import uuid as _uuid

from data.ChromelessRootData import ChromelessRootData


@dataclass
class JoyStatsNodeData(ChromelessRootData):
    """The identity of a JoyStatsNode.

    JoyStatsNode is a HUD node — it reads joy state from the main
    window every second and paints a compact stats grid. It never
    participates in the wire graph, which is why it lives on
    ChromelessRoot alongside StickerNode and (soon) ValueNode.

    Viewport pin fields (``pinned``, ``pin_vp_x``, ``pin_vp_y``) live
    on ChromelessRootData and serialise through super().to_dict() —
    no per-class bookkeeping needed here.
    """

    node_type: str   = field(default="joy_stats")
    title:     str   = field(default="Joy Stats")
    width:     float = field(default=240.0)
    height:    float = field(default=280.0)

    @classmethod
    def from_dict(cls, data: dict) -> "JoyStatsNodeData":
        return cls(
            node_id       = data.get("node_id", 0),
            title         = data.get("title",   "Joy Stats"),
            uuid          = data.get("uuid",    _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   240.0)),
            height        = float(data.get("height",  280.0)),
            z_value       = float(data.get("z_value",   0.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            # ChromelessRootData pin fields
            pinned        = bool(data.get("pinned",   False)),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
        )
