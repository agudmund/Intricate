#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/JoyStatsNodeData.py JoyStatsNode data class
-Identity and state for the live joy-tamagotchi HUD, including viewport pin for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
import uuid as _uuid

from data.NodeData import NodeData


@dataclass
class JoyStatsNodeData(NodeData):
    """The identity of a JoyStatsNode.

    JoyStatsNode is a HUD node — it reads joy state from the main
    window every second and paints a compact stats grid. It never
    participates in the wire graph (never gets connected to anything),
    so it's a candidate for the same viewport-pin mechanic StickerNode
    uses: right-click to pin to the current screen position, right-click
    again to release. While pinned, the node stays anchored to screen
    coordinates as the canvas pans and zooms underneath it.

    The three pin fields mirror StickerNodeData exactly so the same
    activation / tracking / restore code patterns apply.
    """

    node_type: str = field(default="joy_stats")
    title:     str = field(default="Joy Stats")
    width:     float = field(default=240.0)
    height:    float = field(default=280.0)

    # Viewport pin — same contract as StickerNodeData's pin fields
    pinned:    bool  = field(default=False)
    pin_vp_x:  float = field(default=0.0)
    pin_vp_y:  float = field(default=0.0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["pinned"]   = self.pinned
        data["pin_vp_x"] = self.pin_vp_x
        data["pin_vp_y"] = self.pin_vp_y
        return data

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
            pinned        = bool(data.get("pinned",   False)),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
        )
