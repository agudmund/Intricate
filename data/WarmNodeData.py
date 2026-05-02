#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/WarmNodeData.py warm thought identity
-The shape of a warm thought before any pixels have decided how to render it, For Enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData
from shared_braincell.phrase_picker import randomling as pick_phrase


@dataclass
class WarmNodeData(NodeData):
    """
    The identity of a WarmNode.

    The WarmNode is the main content node — a resizable canvas for free-form
    text with an emoji accent and an editable title. body_text holds the full
    content, emoji holds a single emoji character shown as an accent.
    """

    node_type:  str   = field(default="warm")
    title:      str   = field(default_factory=pick_phrase)
    width:      float = field(default=300.0)
    height:     float = field(default=200.0)

    body_text:  str   = field(default="")       # Main editable content

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["body_text"] = self.body_text
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'WarmNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "New Node"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   300.0)),
            height        = float(data.get("height",  200.0)),
            ports_visible = data.get("ports_visible", False),
            body_text     = data.get("body_text", ""),
            emoji         = "",   # shuffled on load by EmojiButton
        )
