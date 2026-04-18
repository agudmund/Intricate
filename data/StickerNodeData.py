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
    `cache_key` is the primary persistence channel (SHA-256 into the
    shared media cache, byte-preserving).  `source_path` is the
    provenance anchor (where the file lived on disk when it was first
    loaded, used for the drift check).  `image_b64` is a legacy fallback
    for pre-cache sessions — always serialized empty for new stickers.
    """

    node_type:    str   = field(default="sticker")
    title:        str   = field(default="Sticker")
    width:        float = field(default=200.0)
    height:       float = field(default=200.0)
    image_b64:    str   = field(default="")    # Legacy base64 — replaced by cache_key
    cache_key:    str   = field(default="")    # SHA-256 key into Documents/data/cache/
    source_path:  str   = field(default="")    # Absolute path to source on disk (provenance)
    source_size:  int   = field(default=0)     # Cheap drift fingerprint — size in bytes at last check
    source_mtime: float = field(default=0.0)   # Cheap drift fingerprint — mtime at last check
    pinned:       bool  = field(default=False) # True = fixed on screen, ignores pan/zoom
    pin_vp_x:     float = field(default=0.0)   # viewport-relative x when pinned
    pin_vp_y:     float = field(default=0.0)   # viewport-relative y when pinned

    def to_dict(self) -> dict:
        data = super().to_dict()
        # Cache-first persistence.  image_b64 is written only when neither
        # the cache nor a source path is available — the legacy tail path.
        data["cache_key"]    = self.cache_key
        data["source_path"]  = self.source_path
        data["source_size"]  = self.source_size
        data["source_mtime"] = self.source_mtime
        data["image_b64"]    = "" if (self.cache_key or self.source_path) else self.image_b64
        data["pinned"]       = self.pinned
        data["pin_vp_x"]     = self.pin_vp_x
        data["pin_vp_y"]     = self.pin_vp_y
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
            cache_key     = data.get("cache_key",     ""),
            source_path   = data.get("source_path",   ""),
            source_size   = int(data.get("source_size",    0)),
            source_mtime  = float(data.get("source_mtime", 0.0)),
            pinned        = data.get("pinned",        False),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
        )
