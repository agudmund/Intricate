#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/RegistryNode.py node registry viewer
-Renders node_registry.toml as a formatted markdown table for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import subprocess
import sys

from nodes.MarkdownNode import MarkdownNode
from data.RegistryNodeData import RegistryNodeData
from pretty_widgets.graphics.Theme import Theme


class RegistryNode(MarkdownNode):
    """
    Live viewer for node_registry.toml — the creative writing surface
    for Intricate's node vocabulary.

    Renders all registered node types as a markdown table grouped by
    category. Watches the registry file for changes and re-renders
    automatically. Edit button opens the TOML in the system editor.
    """

    def __init__(self, data: RegistryNodeData | None = None):
        if data is None:
            data = RegistryNodeData()
        data.label = self._build_markdown()
        super().__init__(data)

        # Watch registry for live updates
        from utils import registry
        if registry.watcher:
            registry.watcher.changed.connect(self._on_registry_changed)

    def _on_registry_changed(self) -> None:
        """Re-render when node_registry.toml changes."""
        self.data.label = self._build_markdown()
        if self._editor:
            self._editor.setHtml(self._markdown_to_html(self.data.label))

    @staticmethod
    def _build_markdown() -> str:
        """Convert the registry into a readable markdown document."""
        from utils import registry

        lines = ["# Node Registry", ""]

        categories = [
            ("text",    "Text"),
            ("images",  "Images"),
            ("audio",   "Audio"),
            ("visual",  "Visual"),
            ("health",  "Health"),
            ("tools",   "Tools"),
            ("info",    "Info"),
            ("claude",  "Claude"),
        ]

        for cat_key, cat_name in categories:
            nodes = registry.get_nodes_by_category(cat_key)
            # Include non-spawnable nodes too for the full picture
            all_nodes = [
                (k, v) for k, v in registry.get_all_nodes().items()
                if v.get("category") == cat_key
            ]
            actions = registry.get_actions_by_category(cat_key)

            if not all_nodes and not actions:
                continue

            lines.append(f"## {cat_name}")
            lines.append("")
            lines.append("| Node | Status | Tooltip | Notes |")
            lines.append("|------|--------|---------|-------|")

            for key, entry in actions:
                name = entry.get("name", key)
                tooltip = entry.get("tooltip", "")
                lines.append(f"| {name} | action | {tooltip} | |")

            for key, entry in all_nodes:
                name = entry.get("name", key)
                status = entry.get("status", "")
                tooltip = entry.get("tooltip", "")
                notes = entry.get("notes", "")
                spawnable = entry.get("spawnable", True)
                if not spawnable:
                    notes = notes or "auto-spawned"
                lines.append(f"| {name} | {status} | {tooltip} | {notes} |")

            lines.append("")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS — edit in external editor
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        edit_pix = Theme.icon(Theme.iconCodeBrowse, fallback_color="#8a9aaa")
        btn = NodeButton(self, edit_pix, self._open_in_editor)
        btn.setToolTip("Edit node_registry.toml")
        self._buttons.append(btn)

    def _open_in_editor(self) -> None:
        """Open node_registry.toml in the system default editor."""
        from utils.registry import _registry_path
        path = _registry_path()
        if not path.exists():
            return
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        from utils import registry
        if registry.watcher:
            try:
                registry.watcher.changed.disconnect(self._on_registry_changed)
            except RuntimeError:
                pass
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def from_dict(data: dict) -> 'RegistryNode':
        return RegistryNode(RegistryNodeData.from_dict(data))
