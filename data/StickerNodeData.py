#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/StickerNodeData.py StickerNodeData data class
-State for the chromeless alpha-PNG sticker node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class StickerNodeData(NodeData):
    """
    A frameless PNG pinned directly on the canvas.

    No border, no buttons, no chrome — just raw pixels with alpha.
    source_path persists across sessions; image_b64 is the fallback
    for pasted/dropped images with no file on disk.
    """

    node_type:   str   = field(default="sticker")
    title:       str   = field(default="Sticker")
    width:       float = field(default=200.0)
    height:      float = field(default=200.0)
    image_b64:   str   = field(default="")
    source_path: str   = field(default="")
    pinned:      bool  = field(default=False)  # True = fixed on screen, ignores pan/zoom
    pin_vp_x:    float = field(default=0.0)    # viewport-relative x when pinned
    pin_vp_y:    float = field(default=0.0)    # viewport-relative y when pinned

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["image_b64"]   = "" if self.source_path else self.image_b64
        data["source_path"] = self.source_path
        data["pinned"]      = self.pinned
        data["pin_vp_x"]    = self.pin_vp_x
        data["pin_vp_y"]    = self.pin_vp_y
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'StickerNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Sticker"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   200.0)),
            height        = float(data.get("height",  200.0)),
            ports_visible = data.get("ports_visible", False),
            image_b64     = data.get("image_b64",     ""),
            source_path   = data.get("source_path",   ""),
            pinned        = data.get("pinned",        False),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
        )
