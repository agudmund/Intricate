#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - data/PerfNodeData.py PerfNodeData data class
-Identity and pin state for the chromeless performance HUD, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
import uuid as _uuid

from data.ChromelessRootData import ChromelessRootData
from pretty_widgets.graphics.Theme import Theme


@dataclass
class PerfNodeData(ChromelessRootData):
    """The identity of a PerfNode.

    Performance readings are always live — nothing persists except
    geometry, identity, and pin state. The four pin fields (pinned,
    pin_vp_x, pin_vp_y, pin_scale) live on ChromelessRootData and
    serialise through super().to_dict() chaining.

    Width default tracks Theme.perfNodeWidth so settings.toml can
    customise it. Height carries a placeholder default; PerfNode.__init__
    derives the auto-fit height from the actual row count + paint
    layout on fresh construction. Saved sessions restore the persisted
    height (which may be the auto-fit result or a user resize).
    """

    node_type: str   = field(default="perf")
    title:     str   = field(default="Performance")
    width:     float = field(default_factory=lambda: Theme.perfNodeWidth)
    height:    float = field(default=240.0)   # placeholder; auto-fit on fresh node

    @classmethod
    def from_dict(cls, data: dict) -> 'PerfNodeData':
        return cls(
            node_id       = data.get("node_id",       0),
            title         = data.get("title",         "Performance"),
            uuid          = data.get("uuid",          _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   Theme.perfNodeWidth)),
            height        = float(data.get("height",  240.0)),
            z_value       = float(data.get("z_value", 0.0)),
            ports_visible = data.get("ports_visible", False),
            shelf_visible = data.get("shelf_visible", True),
            # ChromelessRootData pin fields
            pinned        = bool(data.get("pinned",   False)),
            pin_vp_x      = float(data.get("pin_vp_x", 0.0)),
            pin_vp_y      = float(data.get("pin_vp_y", 0.0)),
            pin_scale     = float(data.get("pin_scale", 1.0)),
        )
