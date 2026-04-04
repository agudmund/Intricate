#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/AudioNodeData.py AudioNodeData data class
-Identity and state for the AudioNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class AudioNodeData(NodeData):
    """
    The identity of an AudioNode.

    Plays audio files (WAV, MP3, FLAC, OGG, M4A, AAC).
    Persists source path, volume, mute, loop state, and playback position.
    """

    node_type:    str   = field(default="audio")
    title:        str   = field(default="Audio")
    width:        float = field(default=300.0)
    height:       float = field(default=120.0)

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
    def from_dict(cls, data: dict) -> 'AudioNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",      0),
            title         = data.get("title",        "Audio"),
            uuid          = data.get("uuid",         _uuid.uuid4().hex),
            x             = float(data.get("x",      0.0)),
            y             = float(data.get("y",      0.0)),
            width         = float(data.get("width",  300.0)),
            height        = float(data.get("height", 120.0)),
            ports_visible = data.get("ports_visible", False),
            source_path   = data.get("source_path",  ""),
            caption       = data.get("caption",      ""),
            volume        = int(data.get("volume",   50)),
            playback_pos  = int(data.get("playback_pos", 0)),
            looping       = data.get("looping",      False),
            muted         = data.get("muted",        False),
            depth_front   = data.get("depth_front",  False),
            node_tint     = data.get("node_tint",    ""),
        )
