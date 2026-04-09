#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/SessionNode.py SessionNode class
-A utility node for inspecting and importing external session files for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path
from collections import Counter

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.SessionNodeData import SessionNodeData
from pretty_widgets.graphics.Theme import Theme


class SessionNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = True
    """
    Utility node for inspecting and importing external session .json files.

    Drop a session file onto the canvas (or onto this node) to see a summary
    of its contents — node count, type breakdown, connection count. Hit the
    import button to spawn all nodes and connections from that file onto the
    canvas at the SessionNode's position.
    """

    def __init__(self, data: SessionNodeData | None = None):
        if data is None:
            data = SessionNodeData()
        super().__init__(data)
        self.setAcceptDrops(True)
        self._cached_payload: dict | None = None
        self.setBrush(self._bg_color())
        self._apply_depth()

    # ─────────────────────────────────────────────────────────────────────────
    # APPEARANCE
    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        super()._build_buttons()
        from nodes.NodeButton import NodeButton as _NB
        import_pix = Theme.icon(Theme.iconSpawnNodes, fallback_color="#7ab88a")
        self._import_btn = _NB(self, import_pix, self._do_import)
        self._import_btn._sticker_shadow = True
        self._import_btn.setToolTip("Import session nodes onto canvas")
        self._buttons.append(self._import_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # DRAG-DROP (onto this node)
    # ─────────────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() == ".json":
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        """Dropping a .json on an existing SessionNode creates a new SessionNode nearby."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() == ".json":
                scene = self.scene()
                if scene and hasattr(scene, 'add_session_node'):
                    offset = QPointF(40.0, 40.0)
                    scene.add_session_node(
                        pos=self.scenePos() + offset,
                        source_path=path,
                    )
                event.acceptProposedAction()
                return
        event.ignore()

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION FILE HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def load_session_file(self, path: str) -> None:
        """Validate and summarise a session .json file."""
        from utils.session import SessionManager

        self.data.source_path = path
        self.data.session_name = Path(path).stem

        payload = SessionManager.get_session_data(path)
        if payload is None:
            self.data.node_count       = 0
            self.data.connection_count = 0
            self.data.type_breakdown   = "invalid or corrupted"
            self._cached_payload       = None
            self.update()
            return

        nodes = payload.get("nodes", [])
        connections = payload.get("connections", [])

        self.data.node_count       = len(nodes)
        self.data.connection_count = len(connections)
        self.data.description      = payload.get("description", "")

        # Build type breakdown string
        counts = Counter(n.get("node_type", "?") for n in nodes)
        parts = [f"{v} {k}" for k, v in counts.most_common()]
        self.data.type_breakdown = ", ".join(parts) if parts else "empty"

        self._cached_payload = payload
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # IMPORT
    # ─────────────────────────────────────────────────────────────────────────

    def _do_import(self) -> None:
        """Spawn all nodes and connections from the loaded session onto the canvas."""
        from pretty_widgets.utils.logger import setup_logger
        _log = setup_logger("session")

        if not self.data.source_path:
            return

        # Reload from disk if we don't have the payload cached (e.g. restored from session)
        if self._cached_payload is None:
            from utils.session import SessionManager
            self._cached_payload = SessionManager.get_session_data(self.data.source_path)

        if self._cached_payload is None:
            return

        scene = self.scene()
        if scene is None or not hasattr(scene, 'import_session'):
            return

        node_count = len(self._cached_payload.get("nodes", []))
        conn_count = len(self._cached_payload.get("connections", []))
        _log.log(5, "[SessionNode] importing %d nodes, %d connections from %s",
                 node_count, conn_count, self.data.session_name)

        try:
            created = scene.import_session(self._cached_payload, anchor=self.scenePos())
        except Exception:
            _log.exception("[SessionNode] import_session crashed")
            return

        _log.log(5, "[SessionNode] import complete — %d nodes created", len(created))

        # Auto-select all imported nodes
        if created:
            scene.clearSelection()
            for node in created:
                try:
                    node.setSelected(True)
                except RuntimeError:
                    pass  # node may have been removed during import

        self.data.imported = True
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r   = self.rect()
        pad = self._CONTENT_PAD
        top = self._content_top()

        # Title — "Session"
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Session",
        )

        # Body content
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.85)
        y = r.top() + self._body_top()
        line_h = 18

        if not self.data.source_path:
            # Placeholder
            painter.setOpacity(0.5)
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                "Drop a .json session file here",
            )
        else:
            # Filename
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                self.data.session_name,
            )
            y += line_h + 4

            # Description — if present
            if self.data.description:
                painter.setOpacity(0.65)
                desc_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP - 1))
                painter.setFont(desc_font)
                painter.drawText(
                    QRectF(r.left() + pad, y, r.width() - pad * 2, 36),
                    Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                    self.data.description,
                )
                y += line_h + 8
                painter.setOpacity(0.85)
                painter.setFont(body_font)

            # Node count
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                f"{self.data.node_count} nodes, {self.data.connection_count} connections",
            )
            y += line_h + 8

            # Type breakdown — dimmer, word-wrapped
            painter.setOpacity(0.6)
            breakdown_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP - 1))
            painter.setFont(breakdown_font)
            avail_h = r.bottom() - y - 30
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, max(20, avail_h)),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                self.data.type_breakdown,
            )

            # Imported badge
            if self.data.imported:
                painter.setOpacity(0.45)
                badge_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize - 2))
                painter.setFont(badge_font)
                painter.setPen(QColor("#7ab88a"))
                painter.drawText(
                    QRectF(r.left() + pad, r.bottom() - 24, r.width() - pad * 2, 20),
                    Qt.AlignRight | Qt.AlignBottom,
                    "imported",
                )

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._cached_payload = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'SessionNode':
        return SessionNode(SessionNodeData.from_dict(data))
