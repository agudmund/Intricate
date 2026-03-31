#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/TreeNode.py TreeNode class
-Displays a project folder structure via cozy-snapshot.py for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QFontMetrics

from nodes.BaseNode import BaseNode
from data.TreeNodeData import TreeNodeData
from graphics.Theme import Theme


PADDING    = 6.0
TITLE_GAP  = 8.0    # breathing room between title row and tree body


class TreeNode(BaseNode):
    """
    Displays a folder-structure tree captured by cozy-snapshot.py.

    On creation the node runs cozy-snapshot.py for the given project path,
    reads the resulting cozy-tree.txt, and shows it in a scrollable
    monospace text area.  A refresh button re-runs the snapshot.
    """

    def __init__(self, data: TreeNodeData | None = None):
        if data is None:
            data = TreeNodeData()
        super().__init__(data)

        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_tree_view()

        if data.tree_text:
            self._editor.setPlainText(data.tree_text)
        elif data.project_path:
            self.refresh()

    # ─────────────────────────────────────────────────────────────────────────
    # TREE VIEW
    # ─────────────────────────────────────────────────────────────────────────

    def _body_rect(self) -> QRectF:
        r   = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + TITLE_GAP + PADDING
        return QRectF(
            r.x() + PADDING,
            top,
            r.width()  - PADDING * 2,
            r.height() - (top - r.y()) - PADDING,
        )

    def _build_tree_view(self) -> None:
        self._editor = QTextEdit()
        self._editor.setFrameStyle(0)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: 'Cascadia Mono', 'Consolas', monospace;
                font-size: 8pt;
                border: none;
                padding: 2px;
                selection-background-color: {Theme.primaryBorder};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.primaryBorder};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.setGeometry(self._body_rect())
        self._editor_proxy.show()

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT
    # ─────────────────────────────────────────────────────────────────────────

    _SNAPSHOT_SCRIPT = "cozy-snapshot.py"

    def refresh(self) -> None:
        """
        Run cozy-snapshot.py and spawn a *new* TreeNode with the result.

        The current node is left untouched (it may have been manually edited).
        The new node is placed 20px to the right and 20px below this one.
        On first load (no existing tree_text) the result goes directly into
        this node instead so there is something to show immediately.
        """
        project = Path(self.data.project_path)
        if not project.is_dir():
            self._set_text(f"[project not found: {project}]")
            return

        script = shutil.which(self._SNAPSHOT_SCRIPT)
        if not script:
            self._set_text(f"[{self._SNAPSHOT_SCRIPT} not in PATH]")
            return

        try:
            subprocess.run(
                [sys.executable, script, str(project)],
                capture_output=True, text=True, encoding="utf-8",
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            self._set_text(f"[snapshot failed: {e}]")
            return

        tree_file = project / "cozy-tree.txt"
        if not tree_file.exists():
            self._set_text("[cozy-tree.txt not generated]")
            return

        try:
            text = tree_file.read_text(encoding="utf-8")
        except Exception as e:
            self._set_text(f"[read error: {e}]")
            return

        # First-time population — fill this node directly
        if not self.data.tree_text:
            self._set_text(text)
            return

        # Subsequent refreshes — spawn a sibling node so edits are preserved
        scene = self.scene()
        if scene is None:
            self._set_text(text)
            return

        from data.TreeNodeData import TreeNodeData
        new_data = TreeNodeData(
            project_path=self.data.project_path,
            tree_text=text,
        )
        new_node = TreeNode(new_data)
        offset = self.pos() + self.rect().bottomRight() + QPointF(20, 20)
        new_node.setPos(offset)
        scene.addItem(new_node)
        scene.raise_node(new_node)

    @staticmethod
    def _strip_chrome(text: str) -> str:
        """Strip the Cozy Snapshot header and footer so only the tree remains."""
        lines = text.splitlines()
        # Strip header: ✨, Generated:, Location:, and blank lines
        start = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith("✨") or s.startswith("Generated:") or s.startswith("Location:"):
                start = i + 1
            else:
                break
        # Strip footer: separator lines (─), Saved by, Hidden:, Double-click, and trailing blanks
        end = len(lines)
        while end > start:
            s = lines[end - 1].strip()
            if not s or s.startswith("─") or s.startswith("Saved by") or s.startswith("Hidden:") or s.startswith("Double-click"):
                end -= 1
            else:
                break
        # Filter out noise entries and everything nested under backup/
        _HIDE = ("backup/", "backup\\", "📁 backup", "cozy-tree.txt")
        filtered = []
        skip_depth = None   # indentation depth of a hidden subtree root
        for line in lines[start:end]:
            # Measure indentation: count leading non-alphanumeric tree-drawing chars
            stripped = line.lstrip(" │├└─┬┤┼╠╦╟╫╚╗╣╔╝╬═║▌▐░▒▓")
            depth = len(line) - len(stripped)

            # If we're inside a hidden subtree, skip until we return to its depth
            if skip_depth is not None:
                if depth > skip_depth:
                    continue
                skip_depth = None

            # Check if this line itself should be hidden
            if any(h in line for h in _HIDE):
                skip_depth = depth
                continue

            filtered.append(line)
        return "\n".join(filtered)

    def _set_text(self, text: str) -> None:
        self.data.tree_text = text
        if self._editor:
            filtered = self._strip_chrome(text)
            self._editor.setPlainText(filtered)
            self._auto_size(filtered)

    def _auto_size(self, text: str) -> None:
        """Resize the node to fit the filtered tree text as rendered by the editor."""
        if not self._editor:
            return

        doc = self._editor.document().clone()
        # Force a full layout at unconstrained width, then read the result
        doc.setTextWidth(-1)
        ideal_w = doc.idealWidth()
        doc.setTextWidth(ideal_w)
        doc_h = doc.size().height()

        chrome_x = PADDING * 2 + 12   # body inset + editor internal padding + scrollbar
        chrome_y = self._BUTTON_ZONE_H + TITLE_GAP + PADDING * 2 + 8

        new_w = max(200, ideal_w + chrome_x)
        new_h = max(120, doc_h   + chrome_y)

        r = self.rect()
        self.setRect(QRectF(r.x(), r.y(), new_w, new_h))

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        refresh_pix = Theme.icon(Theme.iconTreeRefresh, fallback_color="#8cbea0")
        self._buttons.append(NodeButton(self, refresh_pix, self.refresh))

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        # Sync the project folder name into the title so BaseNode's
        # emoji+title row (anchored in the button zone) paints it.
        if self.data.project_path:
            self.data.title = Path(self.data.project_path).name
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # RESIZE
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)
        if self._editor_proxy:
            self._editor_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._editor_proxy:
            self._editor_proxy.hide()
        self._editor = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        if self._editor:
            self.data.tree_text = self._editor.toPlainText()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'TreeNode':
        return TreeNode(TreeNodeData.from_dict(data))
