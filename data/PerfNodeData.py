#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/PerfNodeData.py PerfNodeData data class
-Identity and state for the PerfNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData
from graphics.Theme import Theme


@dataclass
class PerfNodeData(NodeData):
    """
    The identity of a PerfNode.

    Performance readings are always live — nothing persists except geometry.
    """

    node_type: str   = field(default="perf")
    title:     str   = field(default="Performance")
    width:     float = field(default_factory=lambda: Theme.perfNodeWidth)
    height:    float = field(default_factory=lambda: Theme.perfNodeHeight)

    def to_dict(self) -> dict:
        return super().to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> 'PerfNodeData':
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Performance"),
            uuid          = data.get("uuid",          __import__('uuid').uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   Theme.perfNodeWidth)),
            height        = float(data.get("height",  Theme.perfNodeHeight)),
            ports_visible = data.get("ports_visible", False),
        )
