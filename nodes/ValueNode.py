#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ValueNode.py ValueNode class
-Transparent image-sequence node with PrettySlider scrubber, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re
from pathlib import Path

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from nodes.BaseNode import BaseNode
from data.ValueNodeData import ValueNodeData
from graphics.Theme import Theme
import widgets.PrettySlider as pretty_slider


_IMAGES_DIR = Path(__file__).resolve().parent.parent / "Images" / "Value"
_SLIDER_H   = 28
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def _natural_key(p: Path):
    """Sort numerically so bar10 sorts after bar9, not after bar1."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', p.stem)]


class ValueNode(BaseNode):
    """
    Transparent image-sequence node.

    Fills the node body with the current frame from ./Images/Value/,
    with a PrettySlider at the bottom for scrubbing through frames.
    The node background is fully transparent so image alpha shines through.
    current_frame persists across sessions via ValueNodeData.
    """

    def __init__(self, data: ValueNodeData | None = None):
        if data is None:
            data = ValueNodeData()
        super().__init__(data)

        self._frames: list[Path] = self._scan_frames()
        self._pixmap: QPixmap | None = None

        # ── Slider ────────────────────────────────────────────────────────────
        self._slider = pretty_slider.slider(
            orientation=Qt.Orientation.Horizontal,
        )
        self._slider.setRange(0, max(len(self._frames) - 1, 0))
        self._slider.valueChanged.connect(self._seek)
        self._apply_slider_style()

        self._slider_proxy = QGraphicsProxyWidget(self)
        self._slider_proxy.setWidget(self._slider)
        self._slider_proxy.setGeometry(self._slider_rect())

        # Transparent fill, border stays visible
        self.setBrush(Qt.NoBrush)

        # Restore persisted frame without triggering a second valueChanged
        frame = min(data.current_frame, max(len(self._frames) - 1, 0))
        self._slider.blockSignals(True)
        self._slider.setValue(frame)
        self._slider.blockSignals(False)
        self._seek(frame)

    # ── Slider style ──────────────────────────────────────────────────────────

    def _apply_slider_style(self) -> None:
        """Transparent rail, value_node.png as the handle icon."""
        icon_path = Path(__file__).resolve().parent.parent / "icons" / "value_node.png"
        url  = str(icon_path).replace("\\", "/")
        size = 20
        side = -(size // 2 - 2)   # centre the icon on the invisible groove
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background:    transparent;
                height:        0px;
                border:        none;
            }}
            QSlider::handle:horizontal {{
                image:  url({url});
                width:  {size}px;
                height: {size}px;
                margin: {side}px 0px;
            }}
            QSlider::add-page:horizontal  {{ background: transparent; border: none; }}
            QSlider::sub-page:horizontal  {{ background: transparent; border: none; }}
        """)

    # ── Frame scanning ────────────────────────────────────────────────────────

    @staticmethod
    def _scan_frames() -> list[Path]:
        if not _IMAGES_DIR.is_dir():
            return []
        return sorted(
            [p for p in _IMAGES_DIR.iterdir() if p.suffix.lower() in _IMAGE_EXTS],
            key=_natural_key,
        )

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _slider_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(r.left(), r.bottom() - _SLIDER_H, r.width(), _SLIDER_H)

    def _image_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(r.left(), r.top() + self._BUTTON_ZONE_H, r.width(), r.height() - self._BUTTON_ZONE_H - _SLIDER_H)

    # ── Frame seek ────────────────────────────────────────────────────────────

    def _seek(self, index: int) -> None:
        if not self._frames:
            self._pixmap = None
            self.data.current_frame = 0
            self.update()
            return
        index = max(0, min(index, len(self._frames) - 1))
        self.data.current_frame = index
        self._pixmap = QPixmap(str(self._frames[index]))
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        if not self._pixmap or self._pixmap.isNull():
            return

        clip = QPainterPath()
        clip.addRoundedRect(self.rect(), self.round_radius, self.round_radius)
        painter.setClipPath(clip)

        img_rect  = self._image_rect()
        scaled    = self._pixmap.size().scaled(img_rect.size().toSize(), Qt.KeepAspectRatio)
        x         = img_rect.x() + (img_rect.width()  - scaled.width())  / 2
        y         = img_rect.y() + (img_rect.height() - scaled.height()) / 2
        dest      = QRectF(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(dest.toRect(), self._pixmap)

    # ── Resize ────────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)
        if hasattr(self, '_slider_proxy') and self._slider_proxy:
            self._slider_proxy.setGeometry(self._slider_rect())

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if hasattr(self, '_slider_proxy') and self._slider_proxy:
            self._slider_proxy.hide()
        self._slider = None
        super()._prepare_for_removal()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ValueNode':
        return ValueNode(ValueNodeData.from_dict(data))
