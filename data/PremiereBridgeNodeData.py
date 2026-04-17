#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/PremiereBridgeNodeData.py Premiere bridge data class
-The identity and target address of a PremiereBridgeNode, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class PremiereBridgeNodeData(NodeData):
    """State for a PremiereBridgeNode.

    Layers of state, casually exposed now, with strictness applied where
    it matters:

    - Transport target (host, port) — persisted, configures the wire.
    - Clip address (track, clip) — persisted, names the timeline cell.
    - Handshake expectations (expected_project, expected_sequence) —
      persisted, optional. Empty string = permissive (accept whatever's
      open). Any non-empty value flips the node into strict mode — a
      mismatch yields a chained AboutNode with the offending details.
    - Last-known census (last_fps, last_width, last_height, ...) —
      persisted for reference but not authoritative; overwritten on
      every successful handshake. Useful for the paint readout when
      the wire is briefly down, and for debugging drift.
    - Heartbeat metrics (last_ping_rtt_ms, missed_pongs) — runtime-only.
    """

    node_type: str   = field(default="premiere_bridge")
    title:     str   = field(default="Premiere Bridge")
    width:     float = field(default=340.0)
    height:    float = field(default=220.0)

    # ── Transport target — WebSocket now, swappable for Serial in Phase 2b ──
    host: str = field(default="127.0.0.1")
    port: int = field(default=9914)

    # ── Premiere clip address — which timeline cell packets target ─────────
    target_track: int = field(default=0)
    target_clip:  int = field(default=0)

    # ── Handshake expectations — empty = permissive, non-empty = strict ────
    expected_project:  str = field(default="")
    expected_sequence: str = field(default="")

    # ── Last-known census (from most recent READY) ─────────────────────────
    # Overwritten on every successful handshake. Persisted so the node can
    # paint a meaningful readout even before the wire comes back up.
    last_project_path:  str   = field(default="")
    last_fps:           float = field(default=0.0)
    last_width:         int   = field(default=0)
    last_height:        int   = field(default=0)
    last_video_tracks:  int   = field(default=0)
    last_audio_tracks:  int   = field(default=0)
    last_end_seconds:   float = field(default=0.0)
    last_clip_name:     str   = field(default="")
    last_premiere_ver:  str   = field(default="")
    last_handshake_at:  str   = field(default="")  # ISO timestamp string

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["host"]              = self.host
        data["port"]              = self.port
        data["target_track"]      = self.target_track
        data["target_clip"]       = self.target_clip
        data["expected_project"]  = self.expected_project
        data["expected_sequence"] = self.expected_sequence
        data["last_project_path"] = self.last_project_path
        data["last_fps"]          = self.last_fps
        data["last_width"]        = self.last_width
        data["last_height"]       = self.last_height
        data["last_video_tracks"] = self.last_video_tracks
        data["last_audio_tracks"] = self.last_audio_tracks
        data["last_end_seconds"]  = self.last_end_seconds
        data["last_clip_name"]    = self.last_clip_name
        data["last_premiere_ver"] = self.last_premiere_ver
        data["last_handshake_at"] = self.last_handshake_at
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'PremiereBridgeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Premiere Bridge"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   340.0)),
            height        = float(data.get("height",  220.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            host              = str(data.get("host", "127.0.0.1")),
            port              = int(data.get("port", 9914)),
            target_track      = int(data.get("target_track", 0)),
            target_clip       = int(data.get("target_clip",  0)),
            expected_project  = str(data.get("expected_project",  "")),
            expected_sequence = str(data.get("expected_sequence", "")),
            last_project_path = str(data.get("last_project_path", "")),
            last_fps          = float(data.get("last_fps",       0.0)),
            last_width        = int(data.get("last_width",       0)),
            last_height       = int(data.get("last_height",      0)),
            last_video_tracks = int(data.get("last_video_tracks", 0)),
            last_audio_tracks = int(data.get("last_audio_tracks", 0)),
            last_end_seconds  = float(data.get("last_end_seconds", 0.0)),
            last_clip_name    = str(data.get("last_clip_name",    "")),
            last_premiere_ver = str(data.get("last_premiere_ver", "")),
            last_handshake_at = str(data.get("last_handshake_at", "")),
        )
