#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/AboutNodeData.py AboutNodeData data class
-Identity and state for the AboutNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass(slots=True)
class AboutNodeData(NodeData):
    """
    The identity of an AboutNode.

    A minimal sticky-note node — smaller than a WarmNode, no body editor,
    just a label. Used as a category memo planted near groups of nodes.
    Single line of text, always visible, never edited inline.
    """

    node_type:  str   = field(default="about")
    title:      str   = field(default="Note")
    width:      float = field(default=160.0)
    height:     float = field(default=60.0)

    label:      str   = field(default="")   # The displayed memo text

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["label"] = self.label
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'AboutNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "Note"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   160.0)),
            height        = float(data.get("height",   60.0)),
            ports_visible = data.get("ports_visible", False),
            label         = data.get("label",     ""),
        )
