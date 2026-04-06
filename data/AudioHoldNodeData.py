#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/AudioHoldNodeData.py AudioHoldNodeData data class
-Identity and state for the AudioHoldNode silence placeholder. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class AudioHoldNodeData(NodeData):
    """
    The identity of an AudioHoldNode.

    A silence placeholder with configurable duration.
    The merge node treats it like any AudioNode.
    """

    node_type:    str   = field(default="audio_hold")
    title:        str   = field(default="Hold")
    width:        float = field(default=200.0)
    height:       float = field(default=100.0)

    hold_seconds: float = field(default=2.0)
    source_path:  str   = field(default="")
    caption:      str   = field(default="")
    volume:       int   = field(default=50)
    playback_pos: int   = field(default=0)
    looping:      bool  = field(default=False)
    muted:        bool  = field(default=False)
    depth_front:  bool  = field(default=False)
    node_tint:    str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["hold_seconds"] = self.hold_seconds
        data["source_path"]  = self.source_path
        data["caption"]      = self.caption
        data["volume"]       = self.volume
        data["playback_pos"] = self.playback_pos
        data["looping"]      = self.looping
        data["muted"]        = self.muted
        data["depth_front"]  = self.depth_front
        data["node_tint"]    = self.node_tint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'AudioHoldNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",      0),
            title         = data.get("title",        "Hold"),
            uuid          = data.get("uuid",         _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  200.0)),
            height        = float(data.get("height", 100.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            emoji         = data.get("emoji",        ""),
            hold_seconds  = float(data.get("hold_seconds", 2.0)),
            source_path   = data.get("source_path",  ""),
            caption       = data.get("caption",      ""),
            volume        = int(data.get("volume",   50)),
            playback_pos  = int(data.get("playback_pos", 0)),
            looping       = data.get("looping",      False),
            muted         = data.get("muted",        False),
            depth_front   = data.get("depth_front",  False),
            node_tint     = data.get("node_tint",    ""),
        )
