#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/StickerNode.py StickerNode class
-Chromeless alpha-PNG pinned directly on the canvas for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QImage
from PySide6.QtWidgets import QGraphicsItem, QFileDialog

from nodes.BaseNode import BaseNode
from data.StickerNodeData import StickerNodeData
from pretty_widgets.graphics.Theme import Theme


class StickerNode(BaseNode):
    """
    Frameless, chromeless PNG sticker.

    No buttons, no border, no caption — just the image with its alpha
    channel composited directly onto the canvas.  Double-click to browse
    for a PNG.  Drag to move, corner to resize.
    """

    _Z_FLOOR      = 100.0   # float above regular nodes, same as ValueNode
    _wire_clip    = False
    _wire_at_port = True

    def __init__(self, data: StickerNodeData | None = None):
        if data is None:
            data = StickerNodeData()
        super().__init__(data)

        self._pixmap: QPixmap | None = None

        # Transparent — no background fill, no border
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setBrush(Qt.NoBrush)
        self.setPen(Qt.NoPen)

        self.setZValue(self._Z_FLOOR)

        # Load image from source path or b64
        if data.source_path:
            self._load_from_path(data.source_path)
        elif data.image_b64:
            self._load_from_b64(data.image_b64)

        # Pinned stickers track the viewport — restore pin state from data
        self._pin_connected = False
        if data.pinned:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._activate_pin)

    # ── No chrome ────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        pass

    def _create_ports(self) -> None:
        self.input_ports  = []
        self.output_ports = []

    # ── Image loading ────────────────────────────────────────────────────────

    def _load_from_path(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            self._pixmap = QPixmap(str(p))
            self.data.source_path = str(p)
            if not self._pixmap.isNull():
                self._fit_to_image()
        self.update()

    def _load_from_b64(self, b64: str) -> None:
        raw = base64.b64decode(b64)
        img = QImage()
        img.loadFromData(raw)
        if not img.isNull():
            self._pixmap = QPixmap.fromImage(img)
            self._fit_to_image()
        self.update()

    def _fit_to_image(self) -> None:
        """Set node size to match the image if still at default."""
        if self._pixmap and not self._pixmap.isNull():
            if self.data.width == 200.0 and self.data.height == 200.0:
                # Scale down large images to a reasonable canvas size
                pw, ph = self._pixmap.width(), self._pixmap.height()
                scale = min(400.0 / max(pw, 1), 400.0 / max(ph, 1), 1.0)
                self.data.width  = pw * scale
                self.data.height = ph * scale
                self.setRect(QRectF(0, 0, self.data.width, self.data.height))

    def _encode_b64(self) -> str:
        """Encode the current pixmap as base64 PNG for session persistence."""
        if not self._pixmap or self._pixmap.isNull():
            return ""
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self._pixmap.save(buf, "PNG")
        return base64.b64encode(buf.data().data()).decode("ascii")

    # ── Interaction ──────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._pixmap and not self._pixmap.isNull():
            # Has an image — toggle pin
            self._toggle_pin()
        else:
            # No image yet — browse for one
            path, _ = QFileDialog.getOpenFileName(
                None, "Choose Sticker Image", "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)"
            )
            if path:
                self._load_from_path(path)
        event.accept()

    # ── Viewport pinning ─────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        if self.data.pinned:
            self._deactivate_pin()
        else:
            self._activate_pin()

    def _activate_pin(self) -> None:
        """Pin the sticker to its current viewport position."""
        self.data.pinned = True
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        # Record viewport-relative position
        view = self._get_view()
        if view:
            vp_pos = view.mapFromScene(self.pos())
            self.data.pin_vp_x = vp_pos.x()
            self.data.pin_vp_y = vp_pos.y()
            self._connect_viewport_tracking(view)

    def _deactivate_pin(self) -> None:
        """Unpin — sticker becomes draggable again and moves with the canvas."""
        self.data.pinned = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._disconnect_viewport_tracking()

    def _connect_viewport_tracking(self, view) -> None:
        if self._pin_connected:
            return
        view.horizontalScrollBar().valueChanged.connect(self._on_viewport_changed)
        view.verticalScrollBar().valueChanged.connect(self._on_viewport_changed)
        self._pin_connected = True

    def _disconnect_viewport_tracking(self) -> None:
        if not self._pin_connected:
            return
        view = self._get_view()
        if view:
            try:
                view.horizontalScrollBar().valueChanged.disconnect(self._on_viewport_changed)
                view.verticalScrollBar().valueChanged.disconnect(self._on_viewport_changed)
            except (RuntimeError, TypeError):
                pass
        self._pin_connected = False

    def _on_viewport_changed(self, _value=None) -> None:
        """Scrollbar moved — reposition sticker to maintain viewport-relative pos."""
        view = self._get_view()
        if not view:
            return
        from PySide6.QtCore import QPointF
        scene_pos = view.mapToScene(int(self.data.pin_vp_x), int(self.data.pin_vp_y))
        self.setPos(scene_pos)

    def _get_view(self):
        scene = self.scene()
        if scene and scene.views():
            return scene.views()[0]
        return None

    # ── Cursor hiding during drag ──────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            view = self._get_view()
            if view:
                view.setCursor(Qt.BlankCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            view = self._get_view()
            if view:
                view.unsetCursor()

    # ── Transparency guard ───────────────────────────────────────────────────

    def setBrush(self, brush):
        """Always transparent — NodeBehaviour bg-glow must not fill this node."""
        super().setBrush(Qt.NoBrush)

    # ── Z depth ──────────────────────────────────────────────────────────────

    def setZValue(self, z: float) -> None:
        super().setZValue(max(z, self._Z_FLOOR))

    # ── Paint ────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        """Skip all BaseNode chrome — just the image."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.paint_content(painter)
        painter.restore()

    def paint_content(self, painter: QPainter) -> None:
        if not self._pixmap or self._pixmap.isNull():
            # Placeholder hint
            painter.setPen(Theme.textPrimary)
            painter.drawText(self.rect(), Qt.AlignCenter, "double-click\nto load sticker")
            return

        r = self.rect()
        scaled = self._pixmap.size().scaled(r.size().toSize(), Qt.KeepAspectRatio)
        x = r.x() + (r.width()  - scaled.width())  / 2
        y = r.y() + (r.height() - scaled.height()) / 2
        dest = QRectF(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(dest.toRect(), self._pixmap)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    def boundingRect(self):
        return self.rect()

    # ── Resize ───────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._disconnect_viewport_tracking()
        self._pixmap = None
        super()._prepare_for_removal()

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        if not self.data.source_path and self._pixmap:
            self.data.image_b64 = self._encode_b64()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'StickerNode':
        return StickerNode(StickerNodeData.from_dict(data))
