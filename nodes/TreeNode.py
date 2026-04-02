#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/TreeNode.py TreeNode class
-Displays a project folder structure via an in-process tree walker for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import fnmatch
import os
import random
from pathlib import Path
from typing import Iterator, List, Optional

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, QPushButton,
)
from widgets.PrettyMenu import StyledTextEdit as QTextEdit, StyledLineEdit as QLineEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QIcon

from nodes.BaseNode import BaseNode
from data.TreeNodeData import TreeNodeData
from graphics.Theme import Theme


PADDING      = 6.0
TITLE_GAP    = 8.0    # breathing room between title row and tree body
TOOLBAR_W    = 28.0   # width of the left-hand toolbar strip


# ─────────────────────────────────────────────────────────────────────────────
# IN-PROCESS TREE WALKER  (transplanted from cozy-snapshot.py)
# ─────────────────────────────────────────────────────────────────────────────

class _TreeWalker:
    """
    Walks a directory tree in-process, respecting gitignore and TOML filters.

    Transplanted from cozy-snapshot.py so the TreeNode owns the walk directly —
    no subprocess, no temp file, filters applied at walk time on Path objects.
    """

    _ALWAYS_IGNORE = {".git", "__pycache__"}

    def __init__(
        self,
        root: Path,
        max_depth:     Optional[int]  = None,
        exclude_dirs:  List[str]      = (),
        exclude_exts:  List[str]      = (),
        exclude_files: List[str]      = (),
        show_hidden:   bool           = False,
        use_gitignore: bool           = True,
        use_emoji:     bool           = True,
    ):
        self.root          = root.resolve()
        self.max_depth     = max_depth
        self.exclude_dirs  = set(exclude_dirs) | self._ALWAYS_IGNORE
        self.exclude_exts  = {e.lower() for e in exclude_exts}
        self.exclude_files = set(exclude_files)
        self.show_hidden   = show_hidden
        self.use_emoji     = use_emoji

        if use_gitignore:
            project_root = self._find_project_root(self.root)
            self._patterns = (
                self._load_gitignore(project_root / ".gitignore") +
                self._load_global_gitignore()
            )
        else:
            self._patterns = []

    # ── gitignore helpers ────────────────────────────────────────────────────

    @staticmethod
    def _find_project_root(start: Path) -> Path:
        current = start
        while current != current.parent:
            if (current / ".gitignore").exists():
                return current
            current = current.parent
        return start

    @staticmethod
    def _load_gitignore(path: Path) -> List[str]:
        if not path.exists():
            return []
        patterns = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line.rstrip("/").strip())
        except Exception:
            pass
        return patterns

    @classmethod
    def _load_global_gitignore(cls) -> List[str]:
        home = Path.home()
        for candidate in [
            home / ".gitignore_global",
            home / ".config" / "git" / "ignore",
            home / ".gitignore",
        ]:
            if candidate.exists() and candidate.is_file():
                result = cls._load_gitignore(candidate)
                if result:
                    return result
        return []

    # ── filtering ────────────────────────────────────────────────────────────

    def _should_ignore(self, entry: Path, rel_path: str) -> bool:
        name = entry.name

        if not self.show_hidden and name.startswith("."):
            return True

        if entry.is_dir() and name in self.exclude_dirs:
            return True

        if entry.is_file():
            if entry.suffix.lower() in self.exclude_exts:
                return True
            if name in self.exclude_files:
                return True

        for pattern in self._patterns:
            if (fnmatch.fnmatch(rel_path, pattern) or
                    fnmatch.fnmatch(os.path.basename(rel_path), pattern)):
                return True

        return False

    def _has_visible_content(self, directory: Path) -> bool:
        try:
            for entry in directory.iterdir():
                rel = str(entry.relative_to(self.root))
                if not self._should_ignore(entry, rel):
                    if entry.is_file() or self._has_visible_content(entry):
                        return True
        except (PermissionError, OSError):
            pass
        return False

    # ── walk ─────────────────────────────────────────────────────────────────

    def _walk(self, current: Path, prefix: str, depth: int) -> Iterator[str]:
        if self.max_depth is not None and depth > self.max_depth:
            return

        try:
            entries = sorted(
                current.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except (PermissionError, OSError):
            return

        visible = []
        for entry in entries:
            rel = str(entry.relative_to(self.root))
            if self._should_ignore(entry, rel):
                continue
            if entry.is_dir():
                if self._has_visible_content(entry):
                    visible.append(entry)
            else:
                visible.append(entry)

        if not visible:
            return

        pointers = ["├── "] * (len(visible) - 1) + ["└── "]
        for ptr, entry in zip(pointers, visible):
            is_last = ptr == "└── "
            icon = ("📁 " if entry.is_dir() else "📄 ") if self.use_emoji else ""
            yield f"{prefix}{ptr}{icon}{entry.name}{'/' if entry.is_dir() else ''}"
            if entry.is_dir():
                next_prefix = prefix + ("    " if is_last else "│   ")
                yield from self._walk(entry, next_prefix, depth + 1)

    def build_text(self) -> str:
        lines = list(self._walk(self.root, prefix="", depth=0))
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TREE NODE
# ─────────────────────────────────────────────────────────────────────────────

class TreeNode(BaseNode):
    """
    Displays a folder-structure tree for a given project path.

    The tree is generated in-process by _TreeWalker — no subprocess, no temp
    file.  Filters (depth, excluded dirs/exts/files, gitignore) are driven by
    [node.tree] in settings.toml and applied at walk time on Path objects.
    """

    def __init__(self, data: TreeNodeData | None = None):
        if data is None:
            data = TreeNodeData()

        from utils.IconPicker import emojiIcons
        if not data.emoji or data.emoji == "✨":
            data.emoji = random.choice(emojiIcons)

        super().__init__(data)

        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._toolbar_proxy: QGraphicsProxyWidget | None = None
        self._name_proxy: QGraphicsProxyWidget | None = None
        self._name_editor: QLineEdit | None = None
        self._build_toolbar()
        self._build_name_input()
        self._build_tree_view()

        if data.tree_text:
            self._editor.setPlainText(data.tree_text)
        elif data.project_path:
            self.refresh()

    # ─────────────────────────────────────────────────────────────────────────
    # TREE VIEW
    # ─────────────────────────────────────────────────────────────────────────

    def _toolbar_rect(self) -> QRectF:
        r   = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + TITLE_GAP + PADDING
        return QRectF(
            r.x() + PADDING,
            top,
            TOOLBAR_W,
            r.height() - (top - r.y()) - PADDING,
        )

    def _body_rect(self) -> QRectF:
        r   = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + TITLE_GAP + PADDING
        return QRectF(
            r.x() + PADDING + TOOLBAR_W,
            top,
            r.width()  - PADDING * 2 - TOOLBAR_W,
            r.height() - (top - r.y()) - PADDING,
        )

    def _name_input_rect(self) -> QRectF:
        """Floating input field — spans the body area, one line tall."""
        br = self._body_rect()
        return QRectF(br.x(), br.y(), br.width(), 24.0)

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT TOOLBAR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        btn_size = int(TOOLBAR_W - 4)
        self._tb_new_folder = QPushButton("📁")
        self._tb_new_folder.setToolTip("New Folder")
        self._tb_new_folder.setFixedSize(btn_size, btn_size)
        self._tb_new_folder.setFlat(True)
        self._tb_new_folder.setStyleSheet(f"""
            QPushButton {{
                border: none; padding: 0px;
                background: transparent;
                color: {Theme.textPrimary};
                font-size: 12pt;
            }}
            QPushButton:hover {{
                background: {Theme.primaryBorder};
                border-radius: 4px;
            }}
        """)
        self._tb_new_folder.clicked.connect(self._show_name_input)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        tb_layout = QVBoxLayout(container)
        tb_layout.setContentsMargins(2, 2, 2, 2)
        tb_layout.setSpacing(4)
        tb_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        tb_layout.addWidget(self._tb_new_folder)

        self._toolbar_proxy = QGraphicsProxyWidget(self)
        self._toolbar_proxy.setWidget(container)
        self._toolbar_proxy.setGeometry(self._toolbar_rect())
        self._toolbar_proxy.show()

    # ─────────────────────────────────────────────────────────────────────────
    # NEW FOLDER — NAME INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _build_name_input(self) -> None:
        self._name_editor = QLineEdit()
        self._name_editor.setAlignment(Qt.AlignLeft)
        self._name_editor.setPlaceholderText("folder name…")
        self._name_editor.setFrame(False)
        self._name_editor.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.nodeBg};
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: 1px solid {Theme.primaryBorder};
                border-radius: 4px;
                padding: 2px 6px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._name_editor.returnPressed.connect(self._commit_new_folder)

        self._name_proxy = QGraphicsProxyWidget(self)
        self._name_proxy.setWidget(self._name_editor)
        self._name_proxy.setGeometry(self._name_input_rect())
        self._name_proxy.hide()
        self._name_proxy.setZValue(10)  # float above the tree text

    def _show_name_input(self) -> None:
        self._name_proxy.setGeometry(self._name_input_rect())
        self._name_editor.clear()

        # Lift view focus policy so the embedded QLineEdit can receive keys
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)

        self._name_proxy.show()
        self._name_proxy.setFocus()
        self._name_editor.setFocus(Qt.MouseFocusReason)

    def _commit_new_folder(self) -> None:
        name = self._name_editor.text().strip()
        self._name_proxy.hide()
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)

        if not name or not self.data.project_path:
            return

        from utils.helpers import ensure_dir
        target = Path(self.data.project_path) / name
        if ensure_dir(target):
            self._refresh_in_place()

    def _refresh_in_place(self) -> None:
        """Re-walk the tree, destroy this node (with particles), spawn a fresh one."""
        project = Path(self.data.project_path)
        if not project.is_dir():
            return

        try:
            text = self._make_walker().build_text()
        except Exception:
            return

        scene = self.scene()
        if scene is None:
            return

        pos = self.pos()
        z   = self.zValue()
        w   = self.rect().width()
        h   = self.rect().height()

        # Spawn the replacement first so the canvas is never empty
        new_data = TreeNodeData(
            project_path = self.data.project_path,
            tree_text    = text,
            width        = w,
            height       = h,
        )
        new_node = TreeNode(new_data)
        new_node.setPos(pos)
        new_node.setZValue(z)
        scene.addItem(new_node)

        # Standard particle burst + deferred removal — same path as shake-delete
        from graphics.Particles import sprinkle
        sprinkle(scene, self.mapToScene(self.rect().center()), count=3000)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: scene.removeItem(self))

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
    # SNAPSHOT / REFRESH
    # ─────────────────────────────────────────────────────────────────────────

    def _make_walker(self) -> _TreeWalker:
        """Build a walker from current [node.tree] TOML settings."""
        import utils.settings as _s
        g = lambda *keys, default=None: _s.get_nested(*keys, default)
        return _TreeWalker(
            root          = Path(self.data.project_path),
            max_depth     = g("node", "tree", "max_depth",     default=None),
            exclude_dirs  = g("node", "tree", "exclude_dirs",  default=[]),
            exclude_exts  = g("node", "tree", "exclude_exts",  default=[]),
            exclude_files = g("node", "tree", "exclude_files", default=[]),
            show_hidden   = g("node", "tree", "show_hidden",   default=False),
            use_gitignore = g("node", "tree", "use_gitignore", default=True),
            use_emoji     = g("node", "tree", "use_emoji",     default=True),
        )

    def refresh(self) -> None:
        """
        Walk the project directory and update the displayed tree.

        First-time load fills this node directly.  Subsequent refreshes spawn
        a sibling node so any manual edits to this one are preserved.
        """
        project = Path(self.data.project_path)
        if not project.is_dir():
            self._set_text(f"[project not found: {project}]")
            return

        try:
            text = self._make_walker().build_text()
        except Exception as e:
            self._set_text(f"[walker error: {e}]")
            return

        if not self.data.tree_text:
            self._set_text(text)
            return

        scene = self.scene()
        if scene is None:
            self._set_text(text)
            return

        new_data = TreeNodeData(
            project_path = self.data.project_path,
            tree_text    = text,
        )
        new_node = TreeNode(new_data)
        offset = self.pos() + self.rect().bottomRight() + QPointF(20, 20)
        new_node.setPos(offset)
        scene.addItem(new_node)
        scene.raise_node(new_node)

    def _set_text(self, text: str) -> None:
        self.data.tree_text = text
        if self._editor:
            self._editor.setPlainText(text)
            self._auto_size(text)

    def _auto_size(self, text: str) -> None:
        """Resize the node to fit the tree text as rendered by the editor."""
        if not self._editor:
            return

        doc = self._editor.document().clone()
        doc.setTextWidth(-1)
        ideal_w = doc.idealWidth()
        doc.setTextWidth(ideal_w)
        doc_h = doc.size().height()

        chrome_x = PADDING * 2 + TOOLBAR_W + 12
        chrome_y = self._BUTTON_ZONE_H + TITLE_GAP + PADDING * 2 + 8

        new_w = max(200, ideal_w + chrome_x)
        new_h = max(120, doc_h   + chrome_y)

        r = self.rect()
        self.setRect(QRectF(r.x(), r.y(), new_w, new_h))

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if self._name_proxy and self._name_proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._name_proxy.hide()
                if self.scene() and self.scene().views():
                    self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
                event.accept()
                return
            event.accept()
            return
        super().keyPressEvent(event)

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
        if self.data.project_path:
            self.data.title = Path(self.data.project_path).name
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # RESIZE
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)
        if self._toolbar_proxy:
            self._toolbar_proxy.setGeometry(self._toolbar_rect())
        if self._editor_proxy:
            self._editor_proxy.setGeometry(self._body_rect())
        if self._name_proxy:
            self._name_proxy.setGeometry(self._name_input_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._name_proxy and self._name_proxy.isVisible():
            self._name_proxy.hide()
        if self._toolbar_proxy:
            self._toolbar_proxy.hide()
        if self._editor_proxy:
            self._editor_proxy.hide()
        self._editor = None
        self._name_editor = None
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
