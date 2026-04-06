#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/MergeNode.py MergeNode class
-Lists connected AudioNodes in sequential order as a merge staging area for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.MergeNodeData import MergeNodeData
from pretty_widgets.graphics.Theme import Theme


_LINE_HEIGHT = 18.0    # per-entry row height
_NUM_WIDTH   = 20.0    # space reserved for the index number


class MergeNode(BaseNode):
    """
    Merge staging node — displays connected AudioNodes as a numbered list.

    Connect AudioNodes via ports. The body area paints their captions
    (or filenames if no caption is set) in connection order.
    The list updates live on every repaint.
    """

    _has_depth_toggle = True

    def __init__(self, data: MergeNodeData | None = None):
        if data is None:
            data = MergeNodeData()
        super().__init__(data)

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTED AUDIO NODES
    # ─────────────────────────────────────────────────────────────────────────

    def _get_connected_audio_nodes(self) -> list:
        """Return AudioNodes connected to this node, in connection order."""
        from nodes.AudioNode import AudioNode
        audio_nodes = []
        for conn in self.connections:
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other and isinstance(other, AudioNode):
                audio_nodes.append(other)
        return audio_nodes

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """Draw title via BaseNode, then a numbered list of connected audio files."""
        super().paint_content(painter)

        painter.save()
        r   = self.rect()
        pad = self._CONTENT_PAD
        body_y = r.top() + self._body_top()

        # Body font — smaller than title, matches health/info style
        font = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel))
        painter.setFont(font)

        audio_nodes = self._get_connected_audio_nodes()

        if not audio_nodes:
            # Empty state hint
            painter.setPen(QColor(Theme.textPrimary))
            painter.setOpacity(0.4)
            painter.drawText(
                QRectF(r.left() + pad, body_y,
                       r.width() - pad * 2, _LINE_HEIGHT),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Connect audio nodes..."
            )
            painter.restore()
            return

        # Numbered list
        y = body_y
        for i, node in enumerate(audio_nodes, 1):
            if y + _LINE_HEIGHT > r.bottom() - pad:
                # Overflow indicator
                painter.setPen(QColor(Theme.textPrimary))
                painter.setOpacity(0.4)
                painter.drawText(
                    QRectF(r.left() + pad, y,
                           r.width() - pad * 2, _LINE_HEIGHT),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    f"  +{len(audio_nodes) - i + 1} more..."
                )
                break

            # Index number — dimmer
            painter.setPen(QColor(Theme.primaryBorder))
            painter.drawText(
                QRectF(r.left() + pad, y, _NUM_WIDTH, _LINE_HEIGHT),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{i}."
            )

            # Caption or filename
            label = node.data.caption or Path(node.data.source_path).stem if node.data.source_path else "untitled"
            painter.setPen(QColor(Theme.textPrimary))
            painter.drawText(
                QRectF(r.left() + pad + _NUM_WIDTH + 4, y,
                       r.width() - pad * 2 - _NUM_WIDTH - 4, _LINE_HEIGHT),
                Qt.AlignLeft | Qt.AlignVCenter,
                label
            )

            y += _LINE_HEIGHT

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'MergeNode':
        return MergeNode(MergeNodeData.from_dict(data))
