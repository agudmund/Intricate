#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/NodeSchemaNode.py node schema viewer
-Read-only renderer for Documents/Node Type Schema.md for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from nodes.MarkdownNode import MarkdownNode
from data.NodeSchemaNodeData import NodeSchemaNodeData


class NodeSchemaNode(MarkdownNode):
    """
    Read-only viewer for Documents/Node Type Schema.md.

    Loads the node type schema document from disk at creation.
    Content is stored in data.label for session persistence so the node
    survives even if the file moves.
    """

    _DOC_PATH = Path(__file__).resolve().parent.parent / "Documents" / "Node Type Schema.md"

    def __init__(self, data: NodeSchemaNodeData | None = None):
        if data is None:
            data = NodeSchemaNodeData()
        if not data.label:
            data.label = self._load_doc()
        super().__init__(data)

    @classmethod
    def _load_doc(cls) -> str:
        try:
            return cls._DOC_PATH.read_text(encoding="utf-8")
        except OSError:
            return f"*Could not load {cls._DOC_PATH}*"

    @staticmethod
    def from_dict(data: dict) -> 'NodeSchemaNode':
        return NodeSchemaNode(NodeSchemaNodeData.from_dict(data))
