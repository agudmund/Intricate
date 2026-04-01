#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/PaletteNodeData.py PaletteNodeData data class
-Identity and state for the PaletteNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


def _default_colors():
    return [
        {"label": "Background",  "hex": "#d2d1cf"},
        {"label": "Border",      "hex": "#8a7560"},
        {"label": "Accent",      "hex": "#6b5a47"},
        {"label": "Surface",     "hex": "#2a3a2f"},
        {"label": "Deep",        "hex": "#1e1e1e"},
    ]


@dataclass
class PaletteNodeData(NodeData):
    """
    The identity of a PaletteNode.

    colors holds an ordered list of {"label": str, "hex": str} dicts.
    """

    node_type: str        = field(default="palette")
    title:     str        = field(default="Palette")
    emoji:     str        = field(default="😍")
    width:     float      = field(default=300.0)
    height:    float      = field(default=420.0)
    colors:    list       = field(default_factory=_default_colors)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["colors"] = self.colors
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'PaletteNodeData':
        import uuid as _uuid
        raw_colors = data.get("colors", _default_colors())
        # Backwards compat: convert bare strings to label+hex dicts
        colors = []
        for c in raw_colors:
            if isinstance(c, str):
                colors.append({"label": "Color", "hex": c})
            else:
                colors.append(c)
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "Palette"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  300.0)),
            height        = float(data.get("height", 420.0)),
            ports_visible = data.get("ports_visible", False),
            colors        = colors,
        )
