#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Scene.py IntricateScene class
-The infinite canvas. Holds items, manages the world, owns the purge contract for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import ctypes
import ctypes.wintypes as wt

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor

from pretty_widgets.utils.logger import setup_logger
logger = setup_logger()


def enable_blur(hwnd, tint: QColor = None):
    """Enable Windows Mica blur behind the window via DWM composition.

    AccentState 5 = Mica — the OS provides a frosted glass backdrop
    behind any transparent region of the window.  GradientColor tints
    the blur in ABGR format.
    """
    class AccentPolicy(ctypes.Structure):
        _fields_ = [
            ("AccentState",   ctypes.c_int),
            ("AccentFlags",   ctypes.c_int),
            ("GradientColor", ctypes.c_int),
            ("AnimationId",   ctypes.c_int),
        ]

    class WindowCompositionAttributeData(ctypes.Structure):
        _fields_ = [
            ("Attribute",  ctypes.c_int),
            ("Data",       ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    accent = AccentPolicy()
    accent.AccentState = 5   # Mica
    accent.AccentFlags = 0

    if tint:
        accent.GradientColor = (
            (tint.alpha() << 24) | (tint.blue() << 16)
            | (tint.green() << 8) | tint.red()
        )
    else:
        accent.GradientColor = 0x00000000

    data = WindowCompositionAttributeData()
    data.Attribute  = 19   # WCA_ACCENT_POLICY
    data.SizeOfData = ctypes.sizeof(accent)
    data.Data       = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)

    ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.pointer(data))
    logger.info("DWM Mica blur enabled")


class IntricateScene(QGraphicsScene):
    """
    The world.

    All nodes enter the scene through creation methods here.
    The scene enforces constraints (one HealthNode, spawn position logic)
    and will own the purge contract and node registry when sessions arrive.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Tight focal area for the experimental phase.
        # Cat strategy: certain ground first, expand when ready.
        self.setSceneRect(-500.0, -500.0, 1000.0, 1000.0)

        self._floating_conn = None   # Connection being drawn, None when idle
        self._last_deleted  = None   # dict snapshot of the most recently shake-deleted node

        # Monotonic counters — incremented each time a node is raised.
        # Keeps same-tier nodes ordered by recency without crossing z-tiers.
        self._back_z_top  = -10.0
        self._front_z_top =  10.0

    def helpEvent(self, event) -> None:
        """Route scene item tooltips through PrettyTooltip instead of native rendering."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else __import__('PySide6.QtGui', fromlist=['QTransform']).QTransform())
        if item:
            tip = item.toolTip()
            if tip:
                from pretty_widgets.PrettyTooltip import PrettyTooltip
                PrettyTooltip.instance().show_tip(tip, event.screenPos())
                event.accept()
                return
        # Hide if hovering over empty space
        from pretty_widgets.PrettyTooltip import PrettyTooltip
        t = PrettyTooltip.instance()
        if t.isVisible():
            t.hide()
        event.accept()

    def raise_node(self, node) -> None:
        """Bring node to the top of its z-tier (back or front)."""
        is_front = getattr(node.data, 'depth_front', False)
        if is_front:
            self._front_z_top += 0.001
            node.setZValue(self._front_z_top)
        else:
            self._back_z_top += 0.001
            node.setZValue(self._back_z_top)

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTION WIRING
    # ─────────────────────────────────────────────────────────────────────────

    def begin_connection(self, start_node) -> None:
        """Start drawing a wire from start_node's output port."""
        from graphics.Connection import Connection
        if self._floating_conn:
            self.cancel_connection()
        conn = Connection(start_node)
        self._floating_conn = conn
        self.addItem(conn)

    def update_floating_connection(self, scene_pos: QPointF) -> None:
        """Track the mouse position while a wire is being drawn."""
        if self._floating_conn:
            self._floating_conn.update_path(scene_pos)

    def complete_connection(self, end_node, explicit_port=None) -> None:
        """Snap the floating wire to end_node's input port."""
        if not self._floating_conn:
            return
        conn = self._floating_conn
        self._floating_conn = None
        if conn.start_node is end_node:
            self._discard_connection(conn)
            return
        conn.end_node = end_node
        if explicit_port is not None:
            conn.end_input_port = explicit_port
        # Corner routing is now fully dynamic in Connection.update_path —
        # end_input_port is retained only for explicit overrides (e.g. clicking a specific port).
        end_node.connections.append(conn)
        conn.update_path()

    def cancel_connection(self) -> None:
        """Discard the floating wire without completing it."""
        if self._floating_conn:
            self._discard_connection(self._floating_conn)
            self._floating_conn = None

    def _discard_connection(self, conn) -> None:
        try:
            conn.start_node.connections.remove(conn)
        except ValueError:
            pass
        self.removeItem(conn)

    # ─────────────────────────────────────────────────────────────────────────
    # NODE CREATION
    # ─────────────────────────────────────────────────────────────────────────

    def add_health_node(self, pos: QPointF | None = None):
        """
        Add a HealthNode at pos. One per scene — returns existing if present.
        """
        from nodes.HealthNode import HealthNode

        for item in self.items():
            if isinstance(item, HealthNode):
                return item

        node = HealthNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_perf_node(self, pos: QPointF | None = None):
        """Add a PerfNode at pos. One per scene — returns existing if present."""
        from nodes.PerfNode import PerfNode
        for item in self.items():
            if isinstance(item, PerfNode):
                return item
        node = PerfNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_warm_node(self, pos: QPointF | None = None):
        """Add a WarmNode at pos."""
        from nodes.WarmNode import WarmNode
        node = WarmNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def _random_palette_color(self) -> str | None:
        """Return a random hex string sampled from all PaletteNodes in the scene."""
        import random
        from PySide6.QtGui import QColor
        hexes = []
        for item in self.items():
            d = getattr(item, 'data', None)
            if d and hasattr(d, 'colors'):
                if hasattr(item, 'sync_data'):
                    item.sync_data()
                for c in d.colors:
                    h = c.get('hex', '')
                    if h and QColor(h).isValid():
                        hexes.append(h)
        return random.choice(hexes) if hexes else None

    def add_about_node(self, pos: QPointF | None = None, label: str | None = None):
        """Add an AboutNode at pos, defaulting to forest-green tint."""
        from nodes.AboutNode import AboutNode
        from data.AboutNodeData import AboutNodeData
        data = AboutNodeData(label=label) if label is not None else AboutNodeData()
        node = AboutNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_claude_response_node(self, pos: QPointF | None = None, label: str = "", node_tint: str = ""):
        """Add a ClaudeResponseNode (multiline reply sticky) at pos."""
        from nodes.ClaudeResponseNode import ClaudeResponseNode
        from data.ClaudeResponseNodeData import ClaudeResponseNodeData
        from PySide6.QtCore import QPointF
        node = ClaudeResponseNode(ClaudeResponseNodeData(label=label, node_tint=node_tint))
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    @staticmethod
    def _claude_folder_for(project_path: 'Path | None' = None) -> str:
        """Derive the ~/.claude/projects/... folder path for a given Desktop project path."""
        from pathlib import Path
        if project_path is None:
            project_path = Path.cwd()
        project_path = Path(project_path).resolve()
        slug = str(project_path).replace(":", "-").replace("\\", "-").replace("/", "-")
        return str(Path.home() / ".claude" / "projects" / slug)

    def add_claude_node(self, pos: QPointF | None = None, **_):
        """Add a ClaudeNode at pos. Always connects to the default session folder."""
        from nodes.ClaudeNode import ClaudeNode
        from data.ClaudeNodeData import ClaudeNodeData
        from pretty_widgets.graphics.Theme import Theme
        data = ClaudeNodeData(
            width=Theme.claudeDefaultWidth,
            height=Theme.claudeDefaultHeight,
        )
        node = ClaudeNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_claude_info_node(self, pos: QPointF | None = None):
        """Add a ClaudeInfoNode at pos. One per scene — returns existing if present."""
        from nodes.ClaudeInfoNode import ClaudeInfoNode
        from data.ClaudeInfoNodeData import ClaudeInfoNodeData
        for item in self.items():
            if isinstance(item, ClaudeInfoNode):
                return item
        data = ClaudeInfoNodeData(folder_path=self._claude_folder_for())
        node = ClaudeInfoNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_text_node(self, pos: QPointF | None = None, label: str = "",
                      node_tint: str = "", render_html: bool = False):
        """Add a TextNode at pos, optionally pre-filled with label text."""
        from nodes.TextNode import TextNode
        from data.TextNodeData import TextNodeData
        data = TextNodeData(label=label, node_tint=node_tint, render_html=render_html)
        node = TextNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_readme_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a ReadmeNode at pos, optionally pre-filled with markdown text."""
        from nodes.ReadmeNode import ReadmeNode
        from data.ReadmeNodeData import ReadmeNodeData
        data = ReadmeNodeData(label=label)
        node = ReadmeNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_architecture_node(self, pos: QPointF | None = None):
        """Add an ArchitectureNode at pos — loads Documents/Architecture.md."""
        from nodes.ArchitectureNode import ArchitectureNode
        node = ArchitectureNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_node_schema_node(self, pos: QPointF | None = None):
        """Add a NodeSchemaNode at pos — loads Documents/Node Type Schema.md."""
        from nodes.NodeSchemaNode import NodeSchemaNode
        node = NodeSchemaNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_markdown_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a generic MarkdownNode at pos, pre-filled with markdown text."""
        from nodes.MarkdownNode import MarkdownNode
        from data.MarkdownNodeData import MarkdownNodeData
        data = MarkdownNodeData(label=label)
        node = MarkdownNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_registry_node(self, pos: QPointF | None = None):
        """Add a RegistryNode at pos — live viewer for node_registry.toml."""
        from nodes.RegistryNode import RegistryNode
        node = RegistryNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_cushions_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a CushionsNode at pos, optionally pre-filled with label text."""
        from nodes.CushionsNode import CushionsNode
        from data.CushionsNodeData import CushionsNodeData
        data = CushionsNodeData(label=label) if label else CushionsNodeData()
        node = CushionsNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_code_node(self, pos: QPointF | None = None, path: str | None = None,
                      label: str = ""):
        """Add a CodeNode at pos, optionally loading a file or pre-filled with text."""
        from nodes.CodeNode import CodeNode
        from data.CodeNodeData import CodeNodeData
        data = CodeNodeData(label=label) if label else CodeNodeData()
        node = CodeNode(data)
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        if path:
            node.load_from_path(path)
        return node

    def add_bloom_node(self, pos: QPointF | None = None):
        """Add a BloomNode at pos — particle scatter controller."""
        from nodes.BloomNode import BloomNode
        node = BloomNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_null_node(self, pos: QPointF | None = None):
        """Add a NullNode at pos — transparent position anchor."""
        from nodes.NullNode import NullNode
        node = NullNode()
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_log_node(self, pos: QPointF | None = None):
        """Add a LogNode at pos — live tail of the current session log."""
        from nodes.LogNode import LogNode
        from data.LogNodeData import LogNodeData
        node = LogNode(LogNodeData())
        if pos is not None:
            r = node.rect()
            node.setPos(pos - QPointF(r.width() / 2, r.height() / 2))
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_bezier_node(self, pos: QPointF | None = None):
        """Add a BezierNode at pos."""
        from nodes.BezierNode import BezierNode
        node = BezierNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_image_node(self, pos: QPointF | None = None, path: str | None = None):
        """
        Add an ImageNode at pos, optionally loading an image from path.

        Called by the Node button (no path, opens file browser on double-click)
        and by View.dropEvent (path provided directly from the dropped file).
        """
        from nodes.ImageNode import ImageNode

        node = ImageNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)

        if path:
            node.load_from_path(path)

        return node

    def add_video_node(self, pos: QPointF | None = None, path: str | None = None):
        """Add a VideoNode at pos, optionally loading a video from path."""
        from nodes.VideoNode import VideoNode

        node = VideoNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)

        if path:
            node.load_from_path(path)

        return node

    def add_sequence_node(self, pos: QPointF | None = None, folder_path: str | None = None):
        """Add a SequenceNode for scrubbing through an image sequence on disk."""
        from nodes.SequenceNode import SequenceNode
        from data.SequenceNodeData import SequenceNodeData
        data = SequenceNodeData(folder_path=folder_path or "")
        node = SequenceNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_tree_node(self, pos: QPointF | None = None, project_path: str | None = None):
        """Add a TreeNode showing the folder structure for project_path."""
        from nodes.TreeNode import TreeNode
        from data.TreeNodeData import TreeNodeData
        data = TreeNodeData(project_path=project_path or "")
        node = TreeNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_info_node(self, pos: QPointF | None = None):
        """Add an InfoNode displaying version and era."""
        from nodes.InfoNode import InfoNode
        from data.InfoNodeData import InfoNodeData
        node = InfoNode(InfoNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_audio_node(self, pos: QPointF | None = None):
        """Add an AudioNode for audio playback."""
        from nodes.AudioNode import AudioNode
        from data.AudioNodeData import AudioNodeData
        node = AudioNode(AudioNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_merge_node(self, pos: QPointF | None = None):
        """Add a MergeNode for listing connected audio files."""
        from nodes.MergeNode import MergeNode
        from data.MergeNodeData import MergeNodeData
        node = MergeNode(MergeNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_audio_hold_node(self, pos: QPointF | None = None):
        """Add an AudioHoldNode — silence placeholder for merge sequencing."""
        from nodes.AudioHoldNode import AudioHoldNode
        from data.AudioHoldNodeData import AudioHoldNodeData
        node = AudioHoldNode(AudioHoldNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_git_node(self, pos: QPointF | None = None):
        """Add a GitNode showing repo status across all Desktop projects."""
        from nodes.GitNode import GitNode
        from data.GitNodeData import GitNodeData
        node = GitNode(GitNodeData())
        node._first_scan = True   # loading ceremony only on fresh sidebar spawn
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_palette_node(self, pos: QPointF | None = None, colors: list | None = None):
        """Add a PaletteNode at pos, optionally pre-filled with colors."""
        from nodes.PaletteNode import PaletteNode
        from data.PaletteNodeData import PaletteNodeData
        data = PaletteNodeData()
        if colors is not None:
            data.colors = colors
        node = PaletteNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_value_node(self, pos: QPointF | None = None):
        """Add a ValueNode that scrubs through ./Images/Value/ with a slider."""
        from nodes.ValueNode import ValueNode
        from data.ValueNodeData import ValueNodeData
        node = ValueNode(ValueNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_fbx_node(self, pos: QPointF | None = None):
        """Add an FbxNode — placeholder for future 3D model viewing."""
        from nodes.FbxNode import FbxNode
        from data.FbxNodeData import FbxNodeData
        node = FbxNode(FbxNodeData())
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_sticker_node(self, pos: QPointF | None = None, path: str | None = None):
        """Add a chromeless alpha-PNG sticker pinned on the canvas."""
        from nodes.StickerNode import StickerNode
        from data.StickerNodeData import StickerNodeData
        data = StickerNodeData()
        if path:
            data.source_path = path
        node = StickerNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_session_node(self, pos: QPointF | None = None, source_path: str | None = None):
        """Add a SessionNode for inspecting and importing session files."""
        from nodes.SessionNode import SessionNode
        from data.SessionNodeData import SessionNodeData
        data = SessionNodeData()
        node = SessionNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        if source_path:
            node.load_session_file(source_path)
        return node

    def add_joy_stats_node(self, pos: QPointF | None = None):
        """Add a JoyStatsNode for live tamagotchi debug display."""
        from nodes.JoyStatsNode import JoyStatsNode
        node = JoyStatsNode()
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    # ─────────────────────────────────────────────────────────────────────────
    # PROJECT IMAGE SYNC
    # ─────────────────────────────────────────────────────────────────────────

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

    def sync_project_images(self, project_folder) -> None:
        """
        Reconcile the canvas against the project's ./Images/ folder.

        Reads session data first (already loaded) — any ImageNode whose
        source_path resolves to a file in ./Images/ is considered tracked.
        New files found on disk that aren't tracked yet each get a fresh
        ImageNode spawned below the existing canvas content.

        Called after every session load (including blank sessions) so that
        dropping a file into ./Images/ on disk surfaces it automatically
        the next time that project is opened.
        """
        from pathlib import Path
        from nodes.ImageNode import ImageNode

        project_folder = Path(project_folder)
        images_dir = project_folder / "Images"
        if not images_dir.is_dir():
            return

        # Collect paths already tracked by existing ImageNodes in the scene
        tracked = set()
        for item in self.items():
            if isinstance(item, ImageNode):
                sp = item.data.source_path
                if sp:
                    try:
                        tracked.add(Path(sp).resolve())
                    except Exception:
                        pass

        # Find image files in ./Images/ not yet on canvas
        new_files = [
            p for p in sorted(images_dir.iterdir())
            if p.is_file()
            and p.suffix.lower() in self._IMAGE_EXTS
            and p.resolve() not in tracked
        ]

        if not new_files:
            return

        # Place new nodes in a grid below all existing canvas content
        W, H, GAP, COLS = 280.0, 220.0, 20.0, 4
        bounds = self.itemsBoundingRect()
        start_x = bounds.left()  if not bounds.isNull() else 20.0
        start_y = bounds.bottom() + GAP * 2 if not bounds.isNull() else 20.0

        for i, path in enumerate(new_files):
            col = i % COLS
            row = i // COLS
            x = start_x + col * (W + GAP)
            y = start_y + row * (H + GAP)
            self.add_image_node(pos=QPointF(x, y), path=str(path))

    # ─────────────────────────────────────────────────────────────────────────
    # VIDEO VIEWPORT CULLING
    # ─────────────────────────────────────────────────────────────────────────

    def update_video_visibility(self, viewport_rect) -> None:
        """Pause/resume VideoNodes and AudioNodes based on viewport intersection."""
        from nodes.VideoNode import VideoNode
        from nodes.AudioNode import AudioNode
        from PySide6.QtCore import QRectF

        # Add a margin so media spins up slightly before scrolling into view
        margin = 200.0
        padded = viewport_rect.adjusted(-margin, -margin, margin, margin)

        for item in self.items():
            if isinstance(item, (VideoNode, AudioNode)):
                node_rect = item.mapRectToScene(item.rect())
                item._set_viewport_visible(padded.intersects(node_rect))

    def pause_all_videos(self) -> None:
        """Unconditionally pause every VideoNode and AudioNode — used when curtains collapse."""
        from nodes.VideoNode import VideoNode
        from nodes.AudioNode import AudioNode
        for item in self.items():
            if isinstance(item, (VideoNode, AudioNode)):
                item._set_viewport_visible(False)

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION PERSISTENCE
    # ─────────────────────────────────────────────────────────────────────────

    def save_session(self, path, viewport: dict | None = None) -> None:
        """Serialize all nodes and connections via SessionManager (rotation + checksum)."""
        from nodes.BaseNode import BaseNode
        from graphics.Connection import Connection
        from utils.session import SessionManager

        nodes = []
        connections = []
        seen = set()

        for item in self.items():
            if isinstance(item, BaseNode):
                nodes.append(item.to_dict())
            elif isinstance(item, Connection) and id(item) not in seen:
                seen.add(id(item))
                try:
                    if item.start_node and item.end_node:
                        connections.append({
                            "start_uuid": item.start_node.data.uuid,
                            "end_uuid":   item.end_node.data.uuid,
                        })
                except RuntimeError:
                    pass

        # Preserve existing description if one was loaded with this session
        description = getattr(self, '_session_description', "")

        SessionManager.save_session(str(path), {
            "version":     SessionManager.VERSION,
            "description": description,
            "nodes":       nodes,
            "connections": connections,
            "viewport":    viewport or {},
        })

        # Garbage-collect orphaned image cache files
        try:
            from utils.image_cache import gc_cache
            live_keys = {
                n.get("cache_key", "") for n in nodes
                if n.get("node_type") == "image" and n.get("cache_key")
            }
            gc_cache(live_keys)
        except Exception:
            pass  # Cache GC failure is non-fatal

    @property
    def session_description(self) -> str:
        """Current session description — read by SessionNode, written by ClaudeNode."""
        return getattr(self, '_session_description', "")

    @session_description.setter
    def session_description(self, value: str) -> None:
        self._session_description = value

    def load_session(self, path) -> dict:
        """Clear the scene and restore from a session.json via SessionManager.

        Returns the viewport dict from the session (may be empty for legacy files).
        """
        from utils.session import SessionManager

        payload = SessionManager.get_session_data(str(path))
        if payload is None:
            return {}

        # Store session description for round-trip persistence
        self._session_description = payload.get("description", "")

        # Suspend BSP indexing during bulk restore — rebuild once at the end.
        # At 1200 nodes this turns O(n²) index rebuilds into a single O(n) pass.
        self.setItemIndexMethod(self.ItemIndexMethod.NoIndex)

        uuid_map = {}
        for d in payload.get("nodes", []):
            try:
                node = self._restore_node(d)
            except Exception:
                logger.exception("Failed to restore %s node (uuid=%s)",
                                 d.get("node_type"), d.get("uuid"))
                node = None
            if node:
                uuid_map[d.get("uuid")] = node

        from graphics.Connection import Connection
        for c in payload.get("connections", []):
            start = uuid_map.get(c.get("start_uuid"))
            end   = uuid_map.get(c.get("end_uuid"))
            if start and end and start is not end:
                try:
                    conn = Connection(start, end)
                    self.addItem(conn)
                    conn.update_path()
                except Exception:
                    logger.exception("Failed to restore connection %s → %s",
                                     c.get("start_uuid"), c.get("end_uuid"))

        # Re-enable BSP indexing — single rebuild for all items
        self.setItemIndexMethod(self.ItemIndexMethod.BspTreeIndex)

        return payload.get("viewport", {})

    def import_session(self, payload: dict, anchor: QPointF) -> list:
        """
        Append nodes and connections from a session payload onto the canvas.

        Unlike load_session(), this does NOT clear the scene first. All imported
        nodes receive fresh UUIDs and their positions are offset so they spawn
        near *anchor* (typically the SessionNode's position).

        Returns the list of created node objects.
        """
        import copy
        import uuid as _uuid

        nodes_raw   = payload.get("nodes", [])
        conns_raw   = payload.get("connections", [])
        if not nodes_raw:
            return []

        logger.log(5, "[import] starting — %d nodes, %d connections",
                    len(nodes_raw), len(conns_raw))

        # ── Compute position offset ──────────────────────────────────────────
        xs = [float(n.get("x", 0.0)) for n in nodes_raw]
        ys = [float(n.get("y", 0.0)) for n in nodes_raw]
        min_x, min_y = min(xs), min(ys)
        offset = anchor - QPointF(min_x, min_y) + QPointF(50.0, 50.0)

        # ── Remap UUIDs and apply offset ─────────────────────────────────────
        old_to_new: dict[str, str] = {}
        prepared: list[dict] = []
        for n in nodes_raw:
            d = copy.deepcopy(n)
            old_uuid = d.get("uuid", "")
            new_uuid = _uuid.uuid4().hex
            old_to_new[old_uuid] = new_uuid
            d["uuid"] = new_uuid
            d["x"] = float(d.get("x", 0.0)) + offset.x()
            d["y"] = float(d.get("y", 0.0)) + offset.y()
            prepared.append(d)

        # ── Restore nodes ────────────────────────────────────────────────────
        uuid_map: dict[str, object] = {}
        created: list = []
        for i, d in enumerate(prepared):
            ntype = d.get("node_type", "?")
            logger.log(5, "[import] restoring node %d/%d type=%s uuid=%s",
                        i + 1, len(prepared), ntype, d.get("uuid", "?")[:8])
            try:
                node = self._restore_node(d)
            except Exception:
                logger.exception("[import] failed to restore node %d type=%s",
                                 i + 1, ntype)
                node = None
            if node:
                uuid_map[d["uuid"]] = node
                created.append(node)

        logger.log(5, "[import] nodes done — %d/%d created, wiring %d connections",
                    len(created), len(prepared), len(conns_raw))

        # ── Wire connections ─────────────────────────────────────────────────
        from graphics.Connection import Connection
        for c in conns_raw:
            new_start = old_to_new.get(c.get("start_uuid", ""))
            new_end   = old_to_new.get(c.get("end_uuid",   ""))
            start = uuid_map.get(new_start)
            end   = uuid_map.get(new_end)
            if start and end and start is not end:
                try:
                    conn = Connection(start, end)
                    self.addItem(conn)
                    conn.update_path()
                except Exception:
                    logger.exception("[import] failed to wire connection")

        logger.log(5, "[import] complete — %d nodes, connections wired", len(created))
        return created

    def _release_all(self) -> None:
        """
        Sever all Qt C++ signal connections so the scene can be GC'd.

        Does NOT call removeItem — that triggers itemChange → _prepare_for_removal
        → _heal_connections which re-entrantly crashes on a half-torn-down scene.
        Instead we just break the C++ signal cycles: behaviour animations, glide
        timers, and node references on connections. Python's cyclic GC handles
        the rest once the C++ pointers no longer prevent collection.
        """
        from nodes.BaseNode import BaseNode
        from graphics.Connection import Connection
        from graphics.Particles import flush_scene

        flush_scene(self)

        from nodes.VideoNode import VideoNode
        from nodes.AudioNode import AudioNode
        from nodes.PerfNode import PerfNode
        from nodes.GitNode import GitNode
        from nodes.WarmNode import WarmNode
        for item in list(self.items()):
            if isinstance(item, BaseNode):
                try:
                    item.behaviour.disconnect_all()
                except Exception:
                    pass
                # Stop poll timers on PerfNodes and GitNodes
                if isinstance(item, (PerfNode, GitNode)):
                    try:
                        item._poll_timer.stop()
                    except Exception:
                        pass
                # Tear down bridge watcher + file so Notepad++ doesn't
                # write stale data into a session that's no longer loaded.
                if isinstance(item, WarmNode):
                    try:
                        item._teardown_bridge()
                    except Exception:
                        pass
                # Stop media players so VideoNodes don't keep decoding in RAM.
                # Defer player.stop() via singleShot so codec teardown doesn't
                # block the UI thread when many videos are open at once.
                # Stop audio players on AudioNodes
                if isinstance(item, AudioNode):
                    try:
                        item._audio.setVolume(0.0)
                        QTimer.singleShot(0, item._player.stop)
                    except Exception:
                        pass
                if isinstance(item, VideoNode):
                    try:
                        item._destroyed = True
                        if item._volume_anim:
                            try:
                                item._volume_anim.finished.disconnect(item._pause_after_fade)
                            except RuntimeError:
                                pass
                            item._volume_anim.stop()
                            item._volume_anim = None
                        item._audio.setVolume(0.0)
                        QTimer.singleShot(0, item._player.stop)
                    except Exception:
                        pass
            elif isinstance(item, Connection):
                try:
                    item._glide_timer.stop()
                    item._glide_timer.timeout.disconnect(item._glide_tick)
                    item.start_node = None
                    item.end_node   = None
                except Exception:
                    pass

    def _clear_all(self) -> None:
        """Tear down every node and connection in the scene cleanly."""
        from nodes.BaseNode import BaseNode
        from graphics.Connection import Connection
        from graphics.Particles import flush_scene

        # Kill any living particles FIRST — they hold scene refs and will
        # dereference stale C++ pointers if the 16 ms tick fires mid-teardown.
        flush_scene(self)

        # Stop all node pulse animations before touching anything
        for item in list(self.items()):
            if isinstance(item, BaseNode):
                try:
                    item.behaviour.disconnect_all()
                except Exception:
                    pass

        # Stop connection glide timers and null node refs before removal.
        # The _glide_timer fires every 16 ms — if it ticks after removeItem
        # but before start_node/end_node are nulled it dereferences a stale
        # C++ pointer and hard-crashes Qt.
        for item in list(self.items()):
            if isinstance(item, Connection):
                try:
                    item._glide_timer.stop()
                    item._glide_timer.timeout.disconnect(item._glide_tick)
                    item.start_node = None
                    item.end_node   = None
                    self.removeItem(item)
                except Exception:
                    pass

        # Tear down each node fully — _prepare_for_removal stops media players,
        # volume animations, and disconnects signals that would otherwise keep
        # VideoNodes alive and decoding in the background until GC runs.
        for item in list(self.items()):
            if isinstance(item, BaseNode):
                try:
                    item._prepare_for_removal()
                    item.connections.clear()
                    self.removeItem(item)
                except Exception:
                    pass

        # Reset z-counters so restored nodes start from a clean slate
        self._back_z_top  = -10.0
        self._front_z_top =  10.0

    def restore_last_deleted(self) -> bool:
        """Recreate the most recently shake-deleted node. Returns True on success."""
        if not self._last_deleted:
            return False
        d = self._last_deleted
        self._last_deleted = None
        node = self._restore_node(d)
        return node is not None

    def _restore_node(self, d: dict):
        """Recreate a single node from its serialized dict."""
        node_type = d.get("node_type", "")
        node = None

        if node_type == "warm":
            from nodes.WarmNode import WarmNode
            from data.WarmNodeData import WarmNodeData
            node = WarmNode(WarmNodeData.from_dict(d))

        elif node_type == "about":
            from nodes.AboutNode import AboutNode
            from data.AboutNodeData import AboutNodeData
            node = AboutNode(AboutNodeData.from_dict(d))

        elif node_type == "bezier":
            from nodes.BezierNode import BezierNode
            from data.BezierNodeData import BezierNodeData
            node = BezierNode(BezierNodeData.from_dict(d))

        elif node_type == "health":
            from nodes.HealthNode import HealthNode
            from data.HealthNodeData import HealthNodeData
            node = HealthNode(HealthNodeData.from_dict(d))

        elif node_type == "claude":
            from nodes.ClaudeNode import ClaudeNode
            from data.ClaudeNodeData import ClaudeNodeData
            node = ClaudeNode(ClaudeNodeData.from_dict(d))

        elif node_type == "claude_response":
            from nodes.ClaudeResponseNode import ClaudeResponseNode
            from data.ClaudeResponseNodeData import ClaudeResponseNodeData
            node = ClaudeResponseNode(ClaudeResponseNodeData.from_dict(d))

        elif node_type == "text":
            from nodes.TextNode import TextNode
            from data.TextNodeData import TextNodeData
            node = TextNode(TextNodeData.from_dict(d))
        elif node_type == "readme":
            from nodes.ReadmeNode import ReadmeNode
            from data.ReadmeNodeData import ReadmeNodeData
            node = ReadmeNode(ReadmeNodeData.from_dict(d))
        elif node_type == "architecture":
            from nodes.ArchitectureNode import ArchitectureNode
            from data.ArchitectureNodeData import ArchitectureNodeData
            node = ArchitectureNode(ArchitectureNodeData.from_dict(d))
        elif node_type == "node_schema":
            from nodes.NodeSchemaNode import NodeSchemaNode
            from data.NodeSchemaNodeData import NodeSchemaNodeData
            node = NodeSchemaNode(NodeSchemaNodeData.from_dict(d))
        elif node_type == "registry":
            from nodes.RegistryNode import RegistryNode
            from data.RegistryNodeData import RegistryNodeData
            node = RegistryNode(RegistryNodeData.from_dict(d))
        elif node_type == "markdown":
            from nodes.MarkdownNode import MarkdownNode
            from data.MarkdownNodeData import MarkdownNodeData
            node = MarkdownNode(MarkdownNodeData.from_dict(d))
        elif node_type == "cushions":
            from nodes.CushionsNode import CushionsNode
            from data.CushionsNodeData import CushionsNodeData
            node = CushionsNode(CushionsNodeData.from_dict(d))
        elif node_type == "code":
            from nodes.CodeNode import CodeNode
            from data.CodeNodeData import CodeNodeData
            node = CodeNode(CodeNodeData.from_dict(d))

        elif node_type == "bloom":
            from nodes.BloomNode import BloomNode
            from data.BloomNodeData import BloomNodeData
            node = BloomNode(BloomNodeData.from_dict(d))

        elif node_type == "null":
            from nodes.NullNode import NullNode
            from data.NullNodeData import NullNodeData
            node = NullNode(NullNodeData.from_dict(d))

        elif node_type == "log":
            from nodes.LogNode import LogNode
            from data.LogNodeData import LogNodeData
            node = LogNode(LogNodeData.from_dict(d))

        elif node_type == "image":
            from nodes.ImageNode import ImageNode
            from data.ImageNodeData import ImageNodeData
            node = ImageNode(ImageNodeData.from_dict(d))

        elif node_type == "video":
            from nodes.VideoNode import VideoNode
            from data.VideoNodeData import VideoNodeData
            node = VideoNode(VideoNodeData.from_dict(d))

        elif node_type == "sequence":
            from nodes.SequenceNode import SequenceNode
            from data.SequenceNodeData import SequenceNodeData
            node = SequenceNode(SequenceNodeData.from_dict(d))

        elif node_type == "tree":
            from nodes.TreeNode import TreeNode
            from data.TreeNodeData import TreeNodeData
            node = TreeNode(TreeNodeData.from_dict(d))

        elif node_type == "info":
            from nodes.InfoNode import InfoNode
            from data.InfoNodeData import InfoNodeData
            node = InfoNode(InfoNodeData.from_dict(d))

        elif node_type == "git":
            from nodes.GitNode import GitNode
            from data.GitNodeData import GitNodeData
            node = GitNode(GitNodeData.from_dict(d))

        elif node_type == "audio":
            from nodes.AudioNode import AudioNode
            from data.AudioNodeData import AudioNodeData
            node = AudioNode(AudioNodeData.from_dict(d))

        elif node_type == "merge":
            from nodes.MergeNode import MergeNode
            from data.MergeNodeData import MergeNodeData
            node = MergeNode(MergeNodeData.from_dict(d))

        elif node_type == "audio_hold":
            from nodes.AudioHoldNode import AudioHoldNode
            from data.AudioHoldNodeData import AudioHoldNodeData
            node = AudioHoldNode(AudioHoldNodeData.from_dict(d))

        elif node_type == "palette":
            from nodes.PaletteNode import PaletteNode
            from data.PaletteNodeData import PaletteNodeData
            node = PaletteNode(PaletteNodeData.from_dict(d))

        elif node_type == "sticker":
            from nodes.StickerNode import StickerNode
            from data.StickerNodeData import StickerNodeData
            node = StickerNode(StickerNodeData.from_dict(d))

        elif node_type == "value":
            from nodes.ValueNode import ValueNode
            from data.ValueNodeData import ValueNodeData
            node = ValueNode(ValueNodeData.from_dict(d))

        elif node_type == "perf":
            from nodes.PerfNode import PerfNode
            from data.PerfNodeData import PerfNodeData
            node = PerfNode(PerfNodeData.from_dict(d))

        elif node_type == "claude_info":
            from nodes.ClaudeInfoNode import ClaudeInfoNode
            from data.ClaudeInfoNodeData import ClaudeInfoNodeData
            node = ClaudeInfoNode(ClaudeInfoNodeData.from_dict(d))

        elif node_type == "fbx":
            from nodes.FbxNode import FbxNode
            from data.FbxNodeData import FbxNodeData
            node = FbxNode(FbxNodeData.from_dict(d))

        elif node_type == "session":
            from nodes.SessionNode import SessionNode
            from data.SessionNodeData import SessionNodeData
            node = SessionNode(SessionNodeData.from_dict(d))

        elif node_type == "joy_stats":
            from nodes.JoyStatsNode import JoyStatsNode
            node = JoyStatsNode.from_dict(d)

        if node is not None:
            node.setPos(QPointF(d.get("x", 0.0), d.get("y", 0.0)))
            self.addItem(node)
            z = float(d.get("z_value", 0.0))
            node.setZValue(z)
            # Keep scene z-counters above all restored values so new nodes
            # always land on top regardless of what was saved.
            if z >= 0:
                self._front_z_top = max(self._front_z_top, z)
            else:
                self._back_z_top  = max(self._back_z_top,  z)

        return node
