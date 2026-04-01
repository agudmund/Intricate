#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Scene.py IntricateScene class
-The infinite canvas. Holds items, manages the world, owns the purge contract for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import QPointF


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

    def add_about_node(self, pos: QPointF | None = None, label: str | None = None):
        """Add an AboutNode at pos."""
        from nodes.AboutNode import AboutNode
        from data.AboutNodeData import AboutNodeData
        data = AboutNodeData(label=label) if label is not None else AboutNodeData()
        node = AboutNode(data)
        if pos is not None:
            node.setPos(pos)
        self.addItem(node)
        self.raise_node(node)
        return node

    def add_claude_response_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a ClaudeResponseNode (multiline reply sticky) at pos."""
        from nodes.ClaudeResponseNode import ClaudeResponseNode
        from data.ClaudeResponseNodeData import ClaudeResponseNodeData
        from PySide6.QtCore import QPointF
        node = ClaudeResponseNode(ClaudeResponseNodeData(label=label))
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
        from graphics.Theme import Theme
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

    def add_text_node(self, pos: QPointF | None = None, label: str = ""):
        """Add a TextNode at pos, optionally pre-filled with label text."""
        from nodes.TextNode import TextNode
        from data.TextNodeData import TextNodeData
        data = TextNodeData(label=label) if label else TextNodeData()
        node = TextNode(data)
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
    # SESSION PERSISTENCE
    # ─────────────────────────────────────────────────────────────────────────

    def save_session(self, path) -> None:
        """Serialize all nodes and connections via SessionManager (rotation + checksum)."""
        from nodes.BaseNode import BaseNode
        from graphics.Connection import Connection
        from utils.session_manager import SessionManager

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

        SessionManager.save_session(str(path), {
            "version":     SessionManager.VERSION,
            "nodes":       nodes,
            "connections": connections,
            "viewport":    {},
        })

    def load_session(self, path) -> None:
        """Clear the scene and restore from a session.json via SessionManager."""
        from utils.session_manager import SessionManager

        payload = SessionManager.get_session_data(str(path))
        if payload is None:
            return

        uuid_map = {}
        for d in payload.get("nodes", []):
            node = self._restore_node(d)
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
                    pass

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

        for item in list(self.items()):
            if isinstance(item, BaseNode):
                try:
                    item.behaviour.disconnect_all()
                except Exception:
                    pass
            elif isinstance(item, Connection):
                try:
                    item._glide_timer.stop()
                    item.start_node = None
                    item.end_node   = None
                except Exception:
                    pass

    def _clear_all(self) -> None:
        """Tear down every node and connection in the scene cleanly."""
        from nodes.BaseNode import BaseNode
        from graphics.Connection import Connection

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
                    item.start_node = None
                    item.end_node   = None
                    self.removeItem(item)
                except Exception:
                    pass

        # Clear each node's connection list then remove it from the scene
        for item in list(self.items()):
            if isinstance(item, BaseNode):
                try:
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

        elif node_type == "image":
            from nodes.ImageNode import ImageNode
            from data.ImageNodeData import ImageNodeData
            node = ImageNode(ImageNodeData.from_dict(d))

        elif node_type == "sequence":
            from nodes.SequenceNode import SequenceNode
            from data.SequenceNodeData import SequenceNodeData
            node = SequenceNode(SequenceNodeData.from_dict(d))

        elif node_type == "tree":
            from nodes.TreeNode import TreeNode
            from data.TreeNodeData import TreeNodeData
            node = TreeNode(TreeNodeData.from_dict(d))

        elif node_type == "palette":
            from nodes.PaletteNode import PaletteNode
            from data.PaletteNodeData import PaletteNodeData
            node = PaletteNode(PaletteNodeData.from_dict(d))

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
