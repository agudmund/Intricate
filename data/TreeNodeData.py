#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/TreeNodeData.py TreeNodeData data class
-Identity and state for the TreeNode. Pure Python, zero Qt for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class TreeNodeData(NodeData):
    """
    The identity of a TreeNode.

    tree_text holds the captured cozy-snapshot output.
    project_path records which folder was snapped.
    """

    node_type:    str   = field(default="tree")
    title:        str   = field(default="Tree")
    emoji:        str   = field(default="✨")
    width:        float = field(default=360.0)
    height:       float = field(default=492.0)
    tree_text:    str   = field(default="")
    project_path: str   = field(default="")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["tree_text"]    = self.tree_text
        data["project_path"] = self.project_path
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'TreeNodeData':
        import uuid as _uuid
        return cls(
            node_id       = data.get("node_id",   0),
            title         = data.get("title",     "Tree"),
            uuid          = data.get("uuid",      _uuid.uuid4().hex),
            x             = float(data.get("x",       0.0)),
            y             = float(data.get("y",       0.0)),
            width         = float(data.get("width",   360.0)),
            height        = float(data.get("height",  492.0)),
            ports_visible = data.get("ports_visible", False),
            tree_text     = data.get("tree_text",    ""),
            project_path  = data.get("project_path", ""),
        )
