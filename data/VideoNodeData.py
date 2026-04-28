#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/VideoNodeData.py VideoNodeData data class
-and the data class quietly shed its audio skin one calm morning
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


# Loop mode cycle: off → loop → pingpong → off → ...
LOOP_MODES = ("off", "loop", "pingpong")


@dataclass
class VideoNodeData(NodeData):
    """
    The identity of a VideoNode.

    source_path points to the video file on disk — videos are never embedded
    as base64 (too large). If the file is missing at restore time the node
    falls through to the cached copy via cache_key, then to a placeholder.

    caption is the editable label shown at the bottom.

    Audio fields (volume, muted) and the boolean `looping` field were retired
    in the PyAV migration — VideoNode no longer carries audio, and looping
    moved to a tri-state `loop_mode`. Old session files carry these legacy
    keys; from_dict reads and ignores volume/muted, and converts a True
    `looping` into `loop_mode="loop"`. Saved sessions written from this
    point forward only emit `loop_mode`.
    """

    node_type: str   = field(default="video")
    title:     str   = field(default="Video")
    width:     float = field(default=360.0)
    height:    float = field(default=280.0)

    source_path:  str   = field(default="")     # Absolute path to source video file — provenance anchor
    cache_key:    str   = field(default="")     # Dotted key into media cache: "<sha256>.<ext>". Once bound, permanent.
    source_size:  int   = field(default=0)      # Cheap drift fingerprint — source file size in bytes at cache time
    source_mtime: float = field(default=0.0)    # Cheap drift fingerprint — source mtime at cache time
    caption:      str   = field(default="")     # Editable label shown on the node
    playback_pos: int   = field(default=0)      # Milliseconds into the video at save time
    loop_mode:    str   = field(default="off")  # "off" | "loop" | "pingpong"
    show_border:  bool  = field(default=True)   # White border around video frame
    was_playing:  bool  = field(default=False)  # Whether video was playing at save time

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["source_path"]   = self.source_path
        data["cache_key"]     = self.cache_key
        data["source_size"]   = self.source_size
        data["source_mtime"]  = self.source_mtime
        data["caption"]       = self.caption
        data["playback_pos"]  = self.playback_pos
        data["loop_mode"]     = self.loop_mode
        data["show_border"]   = self.show_border
        data["was_playing"]   = self.was_playing
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'VideoNodeData':
        import uuid as _uuid

        # Loop mode back-compat: pre-PyAV sessions used a boolean `looping`
        # field. If we don't have a `loop_mode` key, fall back to the bool;
        # if neither exists, default to "off".
        loop_mode = data.get("loop_mode")
        if loop_mode not in LOOP_MODES:
            legacy_looping = bool(data.get("looping", False))
            loop_mode = "loop" if legacy_looping else "off"
        # Audio fields (volume, muted) are silently ignored — VideoNode no
        # longer carries audio. They remain in old session files harmlessly.

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
            cache_key     = data.get("cache_key",     ""),
            source_size   = int(data.get("source_size",   0)),
            source_mtime  = float(data.get("source_mtime", 0.0)),
            caption       = data.get("caption",       ""),
            playback_pos  = data.get("playback_pos",  0),
            loop_mode     = loop_mode,
            show_border   = data.get("show_border",   False),
            was_playing   = data.get("was_playing",   False),
        )
