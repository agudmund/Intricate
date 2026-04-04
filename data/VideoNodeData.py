#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/VideoNodeData.py VideoNodeData data class
-Identity and state for the VideoNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class VideoNodeData(NodeData):
    """
    The identity of a VideoNode.

    source_path points to the video file on disk — videos are never embedded
    as base64 (too large). If the file is missing at restore time the node
    shows a placeholder.

    caption is the editable label shown at the bottom of the node.
    volume is 0–100, persisted so it survives session reload.
    """

    node_type: str   = field(default="video")
    title:     str   = field(default="Video")
    width:     float = field(default=360.0)
    height:    float = field(default=280.0)

    source_path: str   = field(default="")     # Absolute path to source video file
    caption:     str   = field(default="")      # Editable label shown on the node
    volume:      int   = field(default=50)      # 0–100, persisted
    playback_pos: int  = field(default=0)       # Milliseconds into the video at save time
    looping:      bool = field(default=False)   # Whether playback loops
    muted:        bool = field(default=False)   # Whether audio is muted
    show_border:  bool = field(default=False)   # White border around video frame

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["source_path"]   = self.source_path
        data["caption"]       = self.caption
        data["volume"]        = self.volume
        data["playback_pos"]  = self.playback_pos
        data["looping"]       = self.looping
        data["muted"]         = self.muted
        data["show_border"]   = self.show_border
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'VideoNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Video"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   360.0)),
            height        = float(data.get("height",  280.0)),
            ports_visible = data.get("ports_visible", False),
            source_path   = data.get("source_path",   ""),
            caption       = data.get("caption",       ""),
            volume        = data.get("volume",        50),
            playback_pos  = data.get("playback_pos",  0),
            looping       = data.get("looping",       False),
            muted         = data.get("muted",         False),
            show_border   = data.get("show_border",   False),
        )
