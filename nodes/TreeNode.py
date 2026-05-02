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
from shared_braincell.logger import setup_logger

_log = setup_logger("intricate.tree")


PADDING      = 6.0
TITLE_GAP    = 8.0    # breathing room between title row and tree body
TOOLBAR_W    = 28.0   # width of the left-hand toolbar strip
HEART_SIZE   = 18     # heart icon render size (bigger than line height → chain overlap)
HEART_COL_W  = 36     # horizontal space reserved for the heart column.
                      # Heart frame positions at body.x() - 4 with 18 px
                      # frame width. The heart icon's source PNG carries
                      # significant transparent padding — the visible
                      # content's bounding box spans only ~57% of the
                      # 1024 source width (cols 241-822), so the rendered
                      # visible heart shape extends to roughly body.x() + 14
                      # rather than the full frame edge. But the apparent
                      # gap to text is also affected by Qt's HTML text-block
                      # left margin and the QTextEdit's internal viewport
                      # offset, which empirically sit closer to the heart
                      # than the bare CSS math suggests.
                      # Iteration history (2026-05-02): 20 → 28 → 36.
                      # Bump if root-level files at the bottom of a tree
                      # still show first-letter overlap; trim if the gap
                      # starts feeling generous on dense trees.




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

    # _TITLE_RIGHT_PAD left at BaseNode's default (None → symmetric with
    # Theme.nodeTextPaddingLeft). Keeps ~15px visual breathing on the
    # right of long project-folder titles, matching the same pad on the
    # left. Same convention as WarmNode.

    def __init__(self, data: TreeNodeData | None = None):
        if data is None:
            data = TreeNodeData()
        super().__init__(data)

        # Derive the title from the project folder name up front —
        # paint_content keeps it refreshed on every paint, but until that
        # first paint runs the title is still the "Tree" dataclass
        # default. _auto_size (during refresh below) and the title-fit
        # at the end of __init__ both read data.title, so setting it
        # here makes both paths work against the real title instead of
        # the placeholder. Without this the node spawns at default width
        # and the real title clips on first paint.
        if data.project_path:
            self.data.title = Path(data.project_path).name

        self._editor: PrettyEdit | None = None
        self._hearts: list[QGraphicsPixmapItem] = []
        self._heart_pixmap: QPixmap | None = None
        self._toolbar_proxy: QGraphicsProxyWidget | None = None
        self._build_toolbar()
        self._build_tree_view()

        if data.tree_text:
            self._set_text(data.tree_text)
        elif data.project_path:
            self.refresh()

        if data.project_path:
            self._ensure_init_files()
            self._cleanup_legacy()

        # Title-width fit on spawn — mirrors the WarmNode/Markdown-spawn
        # pattern so a long project folder name doesn't clip against the
        # default 200px width before _auto_size gets a chance to run.
        # Grow-only; idempotent if the default already fits.
        self._auto_fit_title_width()

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
    # LEGACY CLEANUP
    # ─────────────────────────────────────────────────────────────────────────

    _LEGACY_FILES = ("cozy-tree.txt",)

    def _cleanup_legacy(self) -> None:
        """Ambient cleanup — remove legacy temp files from the project root."""
        if not self.data.project_path:
            return
        root = Path(self.data.project_path)
        for name in self._LEGACY_FILES:
            legacy = root / name
            if legacy.is_file():
                try:
                    legacy.unlink()
                    _log.info("[cleanup] removed legacy file: %s", legacy)
                except (PermissionError, OSError) as e:
                    _log.debug("[cleanup] could not remove %s: %s", legacy, e)

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT TOOLBAR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        btn_size = int(TOOLBAR_W - 4)
        # Folder icon — sits at the visual root of the tree rendering
        # (slightly larger than inline folder glyphs, so it reads as the
        # root marker). Click-action: open the session's project folder
        # in Windows Explorer. Was previously "plant a new folder" —
        # repurposed 2026-04-22 since project layouts are stable enough
        # now that explicit folder creation from here is no longer a
        # daily utility.
        self._tb_open_explorer = QPushButton("📁")
        self._tb_open_explorer.setToolTip("Open in Windows Explorer")
        from pretty_widgets.PrettyTooltip import install_tooltip
        install_tooltip(self._tb_open_explorer)
        self._tb_open_explorer.setFixedSize(btn_size, btn_size)
        self._tb_open_explorer.setFlat(True)
        self._tb_open_explorer.setStyleSheet(f"""
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
        self._tb_open_explorer.clicked.connect(self._open_in_explorer)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        tb_layout = QVBoxLayout(container)
        tb_layout.setContentsMargins(2, 2, 2, 2)
        tb_layout.setSpacing(4)
        tb_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        tb_layout.addWidget(self._tb_open_explorer)

        self._toolbar_proxy = QGraphicsProxyWidget(self)
        self._toolbar_proxy.setWidget(container)
        self._toolbar_proxy.setToolTip("Open in Windows Explorer")
        self._toolbar_proxy.setGeometry(self._toolbar_rect())
        self._toolbar_proxy.show()

    def _open_in_explorer(self) -> None:
        """Open the session's project root in Windows Explorer, rolling the
        curtains up first so focus lands on the Explorer window cleanly.

        Uses os.startfile(path) — Windows resolves a directory to its
        default handler (Explorer). Silent no-op if the path is missing
        or the OS call fails; the feature is a shortcut, not a
        load-bearing operation.

        Curtains-roll-up mirrors GitNode's "switch to GitHub Desktop"
        pattern (GitNode.py _launch_github_desktop) — same effect: the
        target app takes the foreground because Intricate's shrunken
        itself out of the way, not because we fought for focus.
        """
        if not self.data.project_path:
            return
        project = Path(self.data.project_path)
        if not project.is_dir():
            return
        # Roll up curtains before switching — makes Intricate yield the
        # foreground by getting smaller, not by any explicit focus dance.
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
        except Exception:
            pass
        try:
            os.startfile(str(project))  # Windows: opens folder in Explorer
        except OSError as e:
            _log.debug("[tree] open-in-explorer failed: %s", e)

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
        import shared_braincell.settings as _s
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

    def _auto_fit_title_width(self) -> None:
        """Grow node width if the current title would clip against the
        default. Grow-only — preserves any user corner-drag resize and
        any width already wide enough.

        Body text (the tree area) is unaffected in content: the node
        widens, the body rect widens with it, but the tree text keeps
        its natural left-anchored layout and the extra width becomes
        blank padding on the right. Same pattern as WarmNode's fit so
        long titles and narrow bodies coexist cleanly.

        Formula: title_w + pad*2. BaseNode's _title_rect already reserves
        `pad` on each side (see r.width() - pad*2 in the title rect), so
        a node width of exactly title_w + pad*2 gives the title precisely
        its own advance plus `pad` visible breathing on each edge — no
        extra trailing buffer needed."""
        if not self.data.title:
            return
        r = self.rect()
        # QPainterPath via _measure_title_width — avoids QFontMetrics'
        # known friction with non-monospaced fonts (Chandler42).
        title_w = self._measure_title_width()
        pad = Theme.nodeTextPaddingLeft
        # Must match BaseNode._title_rect's right_pad — both derived
        # from the _TITLE_RIGHT_PAD class constant.
        right_pad = pad if self._TITLE_RIGHT_PAD is None else self._TITLE_RIGHT_PAD
        needed = int(title_w + pad + right_pad)
        _log.debug(
            "[tree-fit] title=%r painted_w=%.1f pad=%s right_pad=%s needed=%d current=%.0f action=%s",
            self.data.title, title_w, pad, right_pad, needed, r.width(),
            "GROW" if needed > r.width() else "no-op",
        )
        if needed > r.width():
            self.prepareGeometryChange()
            self.setRect(QRectF(r.x(), r.y(), needed, r.height()))
            self.data.width = needed
            _log.debug("[tree-fit] post-setRect rect.width=%.0f data.width=%.0f",
                       self.rect().width(), self.data.width)

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

        # Title width budget — left pad plus tight right pad per
        # _TITLE_RIGHT_PAD, matching _auto_fit_title_width and
        # BaseNode._title_rect exactly. Does NOT include TOOLBAR_W — the
        # title sits above the toolbar, not beside it. Uses
        # _measure_title_width (QPainterPath) instead of QFontMetrics —
        # Chandler42 friction point.
        title_pad = Theme.nodeTextPaddingLeft
        title_right_pad = title_pad if self._TITLE_RIGHT_PAD is None else self._TITLE_RIGHT_PAD
        title_w = self._measure_title_width() + title_pad + title_right_pad

        # Width is title-driven only. Body content (tree lines) does NOT
        # widen the node — the body keeps the default width, and long
        # lines clip horizontally if they exceed the body area. Design
        # decision from user: "resize according to the title width while
        # keeping the default width on the body text where the tree is."
        # ideal_w intentionally excluded from the width calculation;
        # doc_h still drives height so every line stays vertically visible.
        default_w = self.data.__class__().width   # TreeNodeData default
        new_w = max(default_w, title_w)
        new_h = max(120, doc_h   + chrome_y)

        r = self.rect()
        _log.debug(
            "[tree-autosize] title=%r title_w_calc=%.1f default_w=%.0f "
            "new_w=%.0f new_h=%.0f (prev rect w=%.0f h=%.0f)",
            self.data.title, title_w, default_w, new_w, new_h,
            r.width(), r.height(),
        )
        self.setRect(QRectF(r.x(), r.y(), new_w, new_h))

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_proxies = ['_toolbar_proxy']

    def _demolition_pre(self) -> None:
        # Hearts are QGraphicsItem children spawned on file operations —
        # remove each from the scene before the node goes. The editor is
        # a PrettyEdit widget with its own teardown contract.
        for h in self._hearts:
            if h.scene():
                h.scene().removeItem(h)
        self._hearts.clear()
        if self._editor:
            self._editor.teardown()
        self._editor = None

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
