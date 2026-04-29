#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/SequenceNode.py SequenceNode class
-Scrubs through an image sequence on disk without touching the Vision API for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QSlider, QFileDialog
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QPainterPath, QFont

from nodes.BaseNode import BaseNode
from data.SequenceNodeData import SequenceNodeData
from pretty_widgets.graphics.Theme import Theme


# Layout constants
HEADER_HEIGHT   = 24.0
SLIDER_HEIGHT   = 20.0
COUNTER_HEIGHT  = 16.0
IMAGE_PADDING   = 6.0
CLIP_RADIUS_MIN = 2.0

# Accepted sequence extensions — common frame formats
_SEQ_EXTS = {".tif", ".tiff", ".exr", ".png", ".jpg", ".jpeg", ".dpx", ".bmp"}


class SequenceNode(BaseNode):
    """
    Displays an image sequence from a folder with a scrub slider.

    No Vision API, no base64 — frames are loaded from disk on demand.
    The slider at the bottom iterates over sorted files in the folder.
    Double-click the image area to pick a folder.

    Layout:
        ┌─────────────────────────┐
        │  header (folder name)   │
        │  ┌───────────────────┐  │
        │  │   image area      │  │
        │  └───────────────────┘  │
        │  [====|──────────────]  │  ← scrub slider
        │  frame 42 / 120        │  ← counter (painted)
        └─────────────────────────┘
    """

    def __init__(self, data: SequenceNodeData | None = None):
        if data is None:
            data = SequenceNodeData()
        super().__init__(data)

        self._frames: list[Path] = []
        self._pixmap: QPixmap | None = None

        # ── Slider ────────────────────────────────────────────────────────────
        self._slider: QSlider | None = None
        self._slider_proxy: QGraphicsProxyWidget | None = None
        self._build_slider()

        # ── Load sequence if path is already set (session restore) ────────────
        if data.folder_path:
            self._scan_folder(data.folder_path)
            self._seek(data.current_frame)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT ZONES
    # ─────────────────────────────────────────────────────────────────────────

    def _image_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x()      + IMAGE_PADDING,
            r.y()      + HEADER_HEIGHT,
            r.width()  - IMAGE_PADDING * 2,
            r.height() - HEADER_HEIGHT - SLIDER_HEIGHT - COUNTER_HEIGHT - IMAGE_PADDING,
        )

    def _slider_rect(self) -> QRectF:
        r = self.rect()
        bottom = r.bottom() - COUNTER_HEIGHT
        return QRectF(
            r.x() + IMAGE_PADDING,
            bottom - SLIDER_HEIGHT,
            r.width() - IMAGE_PADDING * 2,
            SLIDER_HEIGHT,
        )

    def _counter_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + IMAGE_PADDING,
            r.bottom() - COUNTER_HEIGHT,
            r.width() - IMAGE_PADDING * 2,
            COUNTER_HEIGHT,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # SLIDER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_slider(self) -> None:
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.primaryBorder};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.textPrimary};
                width: 10px; height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.backDrop};
                border-radius: 2px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._slider_proxy = QGraphicsProxyWidget(self)
        self._slider_proxy.setWidget(self._slider)
        self._slider_proxy.setGeometry(self._slider_rect())
        self._slider_proxy.show()

    def _on_slider_changed(self, value: int) -> None:
        self._seek(value)

    # ─────────────────────────────────────────────────────────────────────────
    # SEQUENCE LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def _scan_folder(self, folder_path: str) -> None:
        """Scan a directory for image sequence files and configure the slider."""
        folder = Path(folder_path)
        if not folder.is_dir():
            self._frames = []
            return

        self._frames = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in _SEQ_EXTS
        )

        self.data.folder_path = str(folder)
        self.data.title = folder.name

        if self._slider:
            self._slider.setRange(0, max(0, len(self._frames) - 1))
            self._slider.setValue(0)

    def _seek(self, index: int) -> None:
        """Load and display the frame at the given index."""
        if not self._frames:
            self._pixmap = None
            self.data.current_frame = 0
            self.update()
            return

        index = max(0, min(index, len(self._frames) - 1))
        self.data.current_frame = index

        if self._slider and self._slider.value() != index:
            self._slider.setValue(index)

        path = self._frames[index]
        pix = QPixmap(str(path))
        if pix.isNull():
            self._pixmap = None
        else:
            _MAX = 2048
            if pix.width() > _MAX or pix.height() > _MAX:
                pix = pix.scaled(_MAX, _MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._pixmap = pix

        self.update()

    def _open_folder_browser(self) -> None:
        win = self._lower_window()
        scene = self.scene()
        start_dir = scene.get_browse_dir("sequence") if scene else ""
        folder = QFileDialog.getExistingDirectory(
            None, "Select Sequence Folder", start_dir,
        )
        self._raise_window(win)
        if folder:
            if scene:
                scene.remember_browse_dir("sequence", folder)
            self._scan_folder(folder)
            if self._frames:
                self._seek(0)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._image_rect().contains(event.pos()):
            self._open_folder_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r  = self.rect()
        ir = self._image_rect()
        cr = self._counter_rect()

        # ── Header ────────────────────────────────────────────────────────────
        header = QRectF(r.x() + IMAGE_PADDING, r.y() + 4,
                        r.width() - IMAGE_PADDING * 2, HEADER_HEIGHT - 4)
        painter.setPen(QColor(Theme.healthColorLabel))
        painter.setFont(QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel)))
        label = self.data.title if self.data.title != "Sequence" else "double-click to load"
        painter.drawText(header, Qt.AlignLeft | Qt.AlignVCenter, label)

        # ── Image ─────────────────────────────────────────────────────────────
        if self._pixmap and not self._pixmap.isNull():
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - IMAGE_PADDING)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(ir, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            scaled = self._pixmap.scaled(
                ir.width(), ir.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            draw_x = ir.x() + (ir.width()  - scaled.width())  / 2.0
            draw_y = ir.y() + (ir.height() - scaled.height()) / 2.0
            painter.drawPixmap(QPointF(draw_x, draw_y), scaled)
            painter.setClipping(False)
        else:
            painter.setPen(QPen(QColor(Theme.primaryBorder), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(ir, CLIP_RADIUS_MIN, CLIP_RADIUS_MIN)
            painter.setPen(QColor(Theme.healthColorLabel))
            painter.drawText(ir, Qt.AlignCenter, "double-click\nto load sequence")

        # ── Frame counter ─────────────────────────────────────────────────────
        total = len(self._frames)
        if total > 0:
            frame_label = f"{self.data.current_frame + 1} / {total}"
            if self._frames:
                frame_label += f"  {self._frames[self.data.current_frame].name}"
        else:
            frame_label = "no frames"
        painter.setPen(QColor(Theme.healthColorLabel))
        painter.setFont(QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeFooter)))
        painter.drawText(cr, Qt.AlignCenter, frame_label)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # RESIZE
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)
        if self._slider_proxy:
            self._slider_proxy.setGeometry(self._slider_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_proxies = ['_slider_proxy']

    def _demolition_pre(self) -> None:
        # Disconnect the slider's valueChanged — the slider is the
        # inner widget of _slider_proxy and the crew tears it down via
        # setParent(None) + deleteLater() during the proxy walk, but
        # valueChanged must go first.
        if self._slider:
            try:
                self._slider.valueChanged.disconnect(self._on_slider_changed)
            except (RuntimeError, TypeError):
                pass

    def _demolition_post(self) -> None:
        self._slider = None
        self._pixmap = None
        self._frames.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        if self._slider:
            self.data.current_frame = self._slider.value()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'SequenceNode':
        return SequenceNode(SequenceNodeData.from_dict(data))
