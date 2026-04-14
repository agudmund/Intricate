#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ImageNodeData.py ImageNodeData data class
-Identity and state for the ImageNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData
from pretty_widgets.graphics.Theme import Theme


@dataclass
class ImageNodeData(NodeData):
    """
    The identity of an ImageNode.

    image_b64 holds the full image as a base64-encoded PNG string.
    Sessions are self-contained — no file path references, no broken links.
    Large images inflate the session JSON but are always recoverable.

    caption is the editable label shown at the bottom of the node.
    Defaults to the filename stem when loaded from disk.
    """

    node_type: str  = field(default="image")
    title:     str  = field(default="Image")
    width:     float = field(default=280.0)
    height:    float = field(default=220.0)

    image_b64:   str  = field(default="")    # Legacy base64-encoded PNG — replaced by cache_key
    cache_key:   str  = field(default="")    # SHA-256 hash key into Documents/data/cache/
    caption:     str  = field(default="")    # Editable label shown on the node
    source_path: str  = field(default="")    # Absolute path to the source file on disk (provenance)
    show_border:   bool = field(default=False) # Ivory border overlay on the image
    depth_front:   bool = field(default=False)
    shelf_visible: bool = field(default=False) # Button shelf starts collapsed

    def to_dict(self) -> dict:
        data = super().to_dict()
        # Cache replaces base64 — always zero out the blob, keep the hash key.
        # Legacy sessions without cache_key will migrate on first load.
        data["image_b64"]   = ""
        data["cache_key"]   = self.cache_key
        data["caption"]     = self.caption
        data["source_path"] = self.source_path
        data["show_border"]   = self.show_border
        data["depth_front"]   = self.depth_front
        data["shelf_visible"] = self.shelf_visible
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'ImageNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "Image"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   280.0)),
            height        = float(data.get("height",  220.0)),
            ports_visible = data.get("ports_visible", False),
            image_b64     = data.get("image_b64",   ""),
            cache_key     = data.get("cache_key",   ""),
            caption       = data.get("caption",     ""),
            source_path   = data.get("source_path", ""),
            show_border   = data.get("show_border", False),
            depth_front   = data.get("depth_front", False),
            shelf_visible = data.get("shelf_visible", False),
        )
