#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/ImageNodeData.py ImageNodeData data class
-Identity and state for the ImageNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData
from graphics.Theme import Theme


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

    image_b64:   str  = field(default="")    # Base64-encoded PNG — empty until loaded
    caption:     str  = field(default="")    # Editable label shown on the node
    source_path: str  = field(default="")    # Absolute path to the source file on disk (empty for pasted/dropped images)

    def to_dict(self) -> dict:
        data = super().to_dict()
        # Skip the blob when we have a path — reloads from disk on next session open.
        # Only fall back to the full b64 for clipboard/pasted images with no file.
        data["image_b64"]   = "" if self.source_path else self.image_b64
        data["caption"]     = self.caption
        data["source_path"] = self.source_path
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
            caption       = data.get("caption",     ""),
            source_path   = data.get("source_path", ""),
        )
