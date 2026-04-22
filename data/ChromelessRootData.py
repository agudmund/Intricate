#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/ChromelessRootData.py ChromelessRootData data class
-Common data substrate for the chromeless family — holds the pin fields for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field

from data.NodeData import NodeData


@dataclass
class ChromelessRootData(NodeData):
    """Common data substrate for the chromeless family of nodes.

    Sits between NodeData (the identity root) and the three concrete
    data classes (StickerNodeData, ValueNodeData, JoyStatsNodeData, and
    future raw-node siblings). Holds the state fields that every
    chromeless sibling needs — currently just the viewport-pin trio.

    Subclasses add their own type-specific fields (image cache, crop
    rects, frame paths, etc.) and handle their own from_dict. to_dict
    chains cleanly through super() so the pin fields always survive
    serialisation without the subclass having to remember them.
    """

    # Viewport pin — set True when the node is anchored to screen space
    # rather than scene space. Pair pin_vp_x / pin_vp_y are the viewport
    # coordinates (in view-local pixels) the node snaps back to on any
    # pan/zoom of the canvas.
    pinned:   bool  = field(default=False)
    pin_vp_x: float = field(default=0.0)
    pin_vp_y: float = field(default=0.0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["pinned"]   = self.pinned
        data["pin_vp_x"] = self.pin_vp_x
        data["pin_vp_y"] = self.pin_vp_y
        return data
