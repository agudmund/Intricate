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
    QGraphicsPixmapItem, QGraphicsProxyWidget, QGraphicsRectItem,
    QWidget, QVBoxLayout, QPushButton,
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QIcon, QPixmap

from nodes.BaseNode import BaseNode
from data.TreeNodeData import TreeNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("intricate.tree")


PADDING      = 6.0
TITLE_GAP    = 8.0    # breathing room between title row and tree body
TOOLBAR_W    = 28.0   # width of the left-hand toolbar strip
HEART_SIZE   = 18     # heart icon render size (bigger than line height → chain overlap)
HEART_COL_W  = 20     # horizontal space reserved for the heart column




# ─────────────────────────────────────────────────────────────────────────────
# IN-PROCESS TREE WALKER  (transplanted from cozy-snapshot.py)
# ─────────────────────────────────────────────────────────────────────────────

class _TreeWalker:
    """
    Walks a directory tree in-process, respecting gitignore and TOML filters.

    Transplanted from cozy-snapshot.py so the TreeNode owns the walk directly —
    no subprocess, no temp file, filters applied at walk time on Path objects.
    """

    _ALWAYS_IGNORE     = {".git", "__pycache__"}
    _ALWAYS_IGNORE_EXT = {".pkf"}

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
        self.exclude_exts  = {e.lower() for e in exclude_exts} | self._ALWAYS_IGNORE_EXT
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

        if entry.is_dir():
            # Exact name match (e.g. "__pycache__")
            if name in self.exclude_dirs:
                return True
            # Path-based match for nested excludes (e.g. "Documents>data")
            # Uses > as path separator to avoid TOML escape conflicts with / and \
            rel_forward = rel_path.replace("\\", "/")
            for exc in self.exclude_dirs:
                if ">" in exc and rel_forward == exc.replace(">", "/"):
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

        for entry in visible:
            if not self.use_emoji:
                icon = ""
            elif entry.is_file():
                icon = ""
            elif depth > 0:
                icon = "📁 "
            else:
                icon = ""
            yield f"{prefix}{icon}{entry.name}{'/' if entry.is_dir() else ''}"
            if entry.is_dir():
                next_prefix = prefix + "    "
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

    _has_depth_toggle = True

    def __init__(self, data: TreeNodeData | None = None):
        if data is None:
            data = TreeNodeData()
        super().__init__(data)

        self._editor: PrettyEdit | None = None
        self._hearts: list[QGraphicsPixmapItem] = []
        self._heart_pixmap: QPixmap | None = None
        self._toolbar_proxy: QGraphicsProxyWidget | None = None
        self._name_editor: PrettyEdit | None = None
        self._build_toolbar()
        self._build_name_input()
        self._build_tree_view()

        if data.tree_text:
            self._set_text(data.tree_text)
        elif data.project_path:
            self.refresh()

        if data.project_path:
            self._ensure_init_files()

    # ─────────────────────────────────────────────────────────────────────────
    # TREE VIEW
    # ─────────────────────────────────────────────────────────────────────────

    def _toolbar_rect(self) -> QRectF:
        r   = self.rect()
        top = r.y() + self._anim_top_offset + TITLE_GAP + PADDING
        return QRectF(
            r.x() + PADDING,
            top,
            TOOLBAR_W,
            r.height() - (top - r.y()) - PADDING,
        )

    def _body_rect(self) -> QRectF:
        r   = self.rect()
        btn_h = int(TOOLBAR_W - 4) + 2  # toolbar button height + top margin
        line_h = 14                     # approx height of one 8pt mono line
        top = r.y() + self._anim_top_offset + TITLE_GAP + PADDING + btn_h - line_h
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
    # INIT.PY COMPLIANCE
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_init_files(self) -> None:
        """Create missing __init__.py files in Python package subfolders."""
        from utils.helpers import ensure_init_tree
        root = Path(self.data.project_path)
        if root.is_dir():
            ensure_init_tree(root)

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT TOOLBAR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        btn_size = int(TOOLBAR_W - 4)
        self._tb_new_folder = QPushButton("📁")
        self._tb_new_folder.setToolTip("Plant a new folder in the project")
        from pretty_widgets.PrettyTooltip import install_tooltip
        install_tooltip(self._tb_new_folder)
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
        self._toolbar_proxy.setToolTip("Plant a new folder in the project")
        self._toolbar_proxy.setGeometry(self._toolbar_rect())
        self._toolbar_proxy.show()

    # ─────────────────────────────────────────────────────────────────────────
    # NEW FOLDER — NAME INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _build_name_input(self) -> None:
        self._name_editor = PrettyEdit(
            self,
            font_family=Theme.healthFontFamily,
            font_size=9,
            font_color=Theme.textPrimary,
            placeholder="folder name\u2026",
        )
        # Override stylesheet — this input has a visible background and border
        self._name_editor.setStyleSheet(f"""
            QTextEdit {{
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
        self._name_editor.committed.connect(self._on_name_committed)
        self._name_editor.position(self._name_input_rect())
        self._name_editor.proxy.setZValue(10)  # float above the tree text

    def _show_name_input(self) -> None:
        self._name_editor.start_edit("", self._name_input_rect(), select_all=False)

    def _on_name_committed(self, name: str) -> None:
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

        # Standard particle burst + deferred removal — same path as shake-delete.
        # Pre-clear grab, selection, and interaction flags NOW so Qt doesn't
        # route events to this zombie node during the deferred-removal window.
        # _prepare_for_removal() fires later via itemChange when removeItem
        # actually runs, but the dispatch state must be severed immediately.
        self.setSelected(False)
        self.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
        if scene.mouseGrabberItem() is self:
            self.ungrabMouse()
        from graphics.Particles import sprinkle
        sprinkle(scene, self.mapToScene(self.rect().center()), count=8000)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: scene.removeItem(self))

    def _build_tree_view(self) -> None:
        self._editor = PrettyEdit(
            self,
            font_family="Lato",
            font_size=8,
            font_color=Theme.textPrimary,
            always_visible=True,
            scrollbar=False,
        )
        self._editor.position(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT / REFRESH
    # ─────────────────────────────────────────────────────────────────────────

    def _make_walker(self) -> _TreeWalker:
        """Build a walker from current [node.tree] TOML settings."""
        import ast
        import pretty_widgets.utils.settings as _s
        g = lambda *keys, default=None: _s.get_nested(*keys, default)

        def _parse_list(val, default=()):
            """Parse a string-encoded list from TOML, e.g. "['a', 'b']" → ['a', 'b']."""
            if isinstance(val, list):
                return val
            if isinstance(val, str) and val.startswith("["):
                try:
                    result = ast.literal_eval(val)
                    return list(result) if isinstance(result, (list, tuple)) else default
                except Exception:
                    pass
            return default

        def _parse_bool(val, default=False):
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() in ("true", "1", "yes")
            return default

        return _TreeWalker(
            root          = Path(self.data.project_path),
            max_depth     = int(g("node", "tree", "max_depth", default=6) or 6),
            exclude_dirs  = _parse_list(g("node", "tree", "exclude_dirs",  default=[])),
            exclude_exts  = _parse_list(g("node", "tree", "exclude_exts",  default=[])),
            exclude_files = _parse_list(g("node", "tree", "exclude_files", default=[])),
            show_hidden   = _parse_bool(g("node", "tree", "show_hidden",   default=False)),
            use_gitignore = _parse_bool(g("node", "tree", "use_gitignore", default=True)),
            use_emoji     = _parse_bool(g("node", "tree", "use_emoji",     default=True)),
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

    _FILE_ICON = str(Path(__file__).resolve().parent.parent / "icons" / "tree_file_icon.png")

    @staticmethod
    def _tree_to_html(text: str) -> tuple[str, set[int]]:
        """Build HTML and return (html_string, set_of_file_line_indices).

        Each line becomes its own <p> block so QTextDocument creates one
        block per line — required for _place_hearts to map block indices
        to file lines.
        """
        import html as _html
        P = (f'<p style="font-family:Lato; font-size:8pt; '
             f'white-space:pre; margin:0; padding-left:{HEART_COL_W}px;">')
        blocks     = []
        file_lines = set()
        for idx, raw in enumerate(text.split("\n")):
            raw = raw.replace("📄 ", "")
            escaped = _html.escape(raw)
            if raw.rstrip().endswith("/"):
                blocks.append(
                    f'{P}<span style="font-weight:700; color:#ffffff;">{escaped}</span></p>'
                )
            else:
                file_lines.add(idx)
                blocks.append(
                    f'{P}<span style="font-weight:400;">{escaped}</span></p>'
                )
        return "\n".join(blocks), file_lines

    def _set_text(self, text: str) -> None:
        self.data.tree_text = text
        if self._editor:
            html, file_lines = self._tree_to_html(text)
            self._editor.setHtml(html)
            self._auto_size(text)
            self._place_hearts(file_lines)

    def _place_hearts(self, file_lines: set[int]) -> None:
        """Position QGraphicsPixmapItem hearts next to each file line."""
        # Remove old hearts
        for h in self._hearts:
            if h.scene():
                h.scene().removeItem(h)
        self._hearts.clear()

        if not self._editor or not file_lines:
            _log.debug("[hearts] early return — editor=%s  file_lines=%d",
                       self._editor is not None, len(file_lines) if file_lines else 0)
            return

        # Lazy-load the full-res pixmap once — items use setScale() so Qt
        # renders crisp at every zoom level instead of pre-rasterised blur.
        if self._heart_pixmap is None:
            self._heart_pixmap = QPixmap(self._FILE_ICON)
            _log.info("[hearts] pixmap loaded — null=%s  size=%dx%d  path=%s",
                      self._heart_pixmap.isNull(), self._heart_pixmap.width(),
                      self._heart_pixmap.height(), self._FILE_ICON)

        # ── Z-depth compliance ───────────────────────────────────────────
        _log.info("=== TreeNode Z-depth hierarchy ===")
        _log.info("  TreeNode self          z=%s", self.zValue())
        _log.info("  Editor proxy           z=%s", self._editor.proxy.zValue())
        if self._toolbar_proxy:
            _log.info("  Toolbar proxy          z=%s", self._toolbar_proxy.zValue())
        if self._name_editor:
            _log.info("  Name-editor proxy      z=%s", self._name_editor.proxy.zValue())
        _log.info("  Hearts target          z=5")
        _log.info("  File line indices: %s", sorted(file_lines))

        # Force document layout so block rects are valid
        doc = self._editor.document()
        doc.documentLayout().documentSize()

        body  = self._body_rect()
        _log.info("  Body rect: x=%.1f y=%.1f w=%.1f h=%.1f",
                  body.x(), body.y(), body.width(), body.height())

        block = doc.begin()
        idx   = 0
        while block.isValid():
            if idx in file_lines:
                rect = doc.documentLayout().blockBoundingRect(block)
                x = body.x()
                y = body.y() + rect.y()
                heart = QGraphicsPixmapItem(self._heart_pixmap, self)
                heart.setTransformationMode(Qt.SmoothTransformation)
                scale = HEART_SIZE / self._heart_pixmap.width()
                heart.setScale(scale)
                heart.setPos(x - 4, y - 1)
                heart.setZValue(5)
                self._hearts.append(heart)
                _log.debug("  Heart #%d  block=%d  doc_y=%.1f  node_pos=(%.1f, %.1f)  z=%s",
                           len(self._hearts), idx, rect.y(), x, y - 1, heart.zValue())
            block = block.next()
            idx += 1

        _log.info("  Total hearts placed: %d", len(self._hearts))
        _log.info("=== end Z-depth hierarchy ===")

    def _auto_size(self, text: str) -> None:
        """Resize the node to fit the full tree text — no scrollbar needed."""
        if not self._editor:
            return

        doc = self._editor.document()
        # Measure at unconstrained width first to get the ideal width
        prev_tw = doc.textWidth()
        doc.setTextWidth(-1)
        ideal_w = doc.idealWidth()
        # Re-layout at ideal width to get the true document height
        doc.setTextWidth(ideal_w)
        doc_h = doc.size().height()
        # Restore previous text width so setRect re-layouts cleanly
        doc.setTextWidth(prev_tw)

        chrome_x = PADDING * 2 + TOOLBAR_W + 12
        chrome_y = self._BUTTON_ZONE_H + TITLE_GAP + PADDING * 2 + 22

        # Account for title width so long project names don't clip
        from PySide6.QtGui import QFont, QFontMetrics
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_w = QFontMetrics(title_font).horizontalAdvance(self.data.title) + chrome_x

        new_w = max(200, ideal_w + chrome_x, title_w)
        new_h = max(120, doc_h   + chrome_y)

        r = self.rect()
        self.setRect(QRectF(r.x(), r.y(), new_w, new_h))

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if self._name_editor and self._name_editor.proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._name_editor.cancel()
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
        refresh_btn = NodeButton(self, refresh_pix, self.refresh)
        refresh_btn._sticker_shadow = True
        refresh_btn.setToolTip("Take a fresh look at the folder structure")
        self._buttons.append(refresh_btn)

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
        if self._editor:
            self._editor.position(self._body_rect())
        if self._name_editor:
            self._name_editor.position(self._name_input_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        for h in self._hearts:
            if h.scene():
                h.scene().removeItem(h)
        self._hearts.clear()
        if self._name_editor:
            self._name_editor.teardown()
        if self._toolbar_proxy:
            self._toolbar_proxy.setWidget(None)
            self._toolbar_proxy.hide()
            self._toolbar_proxy = None
        if self._editor:
            self._editor.teardown()
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
