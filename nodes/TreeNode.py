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
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.TreeNodeData import TreeNodeData
from graphics.Theme import Theme


HEADER_HEIGHT = 28.0
PADDING       = 6.0


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
        r = self.rect()
        return QRectF(
            r.x() + PADDING,
            r.y() + HEADER_HEIGHT,
            r.width()  - PADDING * 2,
            r.height() - HEADER_HEIGHT - PADDING,
        )

    def _build_tree_view(self) -> None:
        self._editor = QTextEdit()
        self._editor.setReadOnly(True)
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
        """Run cozy-snapshot.py for the project and load cozy-tree.txt."""
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
        if tree_file.exists():
            try:
                text = tree_file.read_text(encoding="utf-8")
                self._set_text(text)
            except Exception as e:
                self._set_text(f"[read error: {e}]")
        else:
            self._set_text("[cozy-tree.txt not generated]")

    def _set_text(self, text: str) -> None:
        self.data.tree_text = text
        if self._editor:
            self._editor.setPlainText(text)

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
        painter.save()
        r = self.rect()

        # Header label
        header = QRectF(r.x() + PADDING, r.y() + 4, r.width() - PADDING * 2, HEADER_HEIGHT - 4)
        painter.setPen(QColor(Theme.healthColorLabel))
        painter.setFont(QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel)))
        label = self.data.title
        if self.data.project_path:
            label = Path(self.data.project_path).name
        painter.drawText(header, Qt.AlignLeft | Qt.AlignVCenter, label)

        painter.restore()

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
