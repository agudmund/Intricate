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
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettySlider import slider as pretty_slider


_IMAGES_DIR = Path(__file__).resolve().parent.parent / "Images" / "Value"
_SLIDER_H   = 32   # tall enough for the 28px handle icon + 2px each side
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
        self._last_crop: tuple = (self._crop_left(), self._crop_right(), self._crop_top(), self._crop_bottom())

        # ── Slider ────────────────────────────────────────────────────────────
        self._slider = pretty_slider(
            orientation=Qt.Orientation.Horizontal,
            handle_size=28,
        )
        self._slider.setRange(0, max(len(self._frames) - 1, 0))
        self._slider.valueChanged.connect(self._seek)
        self._apply_slider_style()

        self._slider_proxy = QGraphicsProxyWidget(self)
        self._slider_proxy.setWidget(self._slider)
        self._slider_proxy.setGeometry(self._slider_rect())

        self.setZValue(self._Z_FLOOR)

        # Transparent fill, border stays visible.
        # DeviceCoordinateCache renders to an opaque pixmap — disable it so
        # NoBrush actually lets the scene background show through.
        from PySide6.QtWidgets import QGraphicsItem
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setBrush(Qt.NoBrush)

        # Proxy widget background must also be transparent
        self._slider.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._slider.setAutoFillBackground(False)

        # Restore persisted frame without triggering a second valueChanged
        frame = min(data.current_frame, max(len(self._frames) - 1, 0))
        self._slider.blockSignals(True)
        self._slider.setValue(frame)
        self._slider.blockSignals(False)
        self._seek(frame)

    # ── No button strip — deletion is via shake ───────────────────────────────

    def _build_buttons(self) -> None:
        pass

    # ── Ports — single W input only ───────────────────────────────────────────

    def _create_ports(self) -> None:
        """One W input port and one E output port, both at the same calibrated Y."""
        from nodes.Port import Port
        in_port  = Port(self, is_output=False)
        out_port = Port(self, is_output=True)
        self.input_ports  = [in_port]
        self.output_ports = [out_port]
        self.input_port   = in_port
        self.output_port  = out_port
        self._place_ports()
        in_port.hide()
        out_port.hide()

    def _place_ports(self) -> None:
        if not self.input_ports:
            return
        import pretty_widgets.utils.settings as _s
        r      = self.rect()
        ox     = 10
        y_off  = float(_s.get_nested("node", "value", "input_port_y_offset", 0))
        x_off  = float(_s.get_nested("node", "value", "input_port_x_offset", 0))
        port_y = r.height() / 2 + self._CAL_PORT_Y + y_off
        self.input_ports[0].setPos(-ox + self._CAL_PORT_X + x_off, port_y)
        if self.output_ports:
            self.output_ports[0].setPos(r.width() + ox - self._CAL_PORT_X - x_off, port_y)

    def closest_input_port(self, scene_pos):
        return self.input_ports[0]

    def closest_output_port(self, scene_pos):
        return self.output_ports[0]

    # ── Slider style ──────────────────────────────────────────────────────────

    def _apply_slider_style(self) -> None:
        """Invisible rail and handle — interaction area only."""
        size = 28
        side = -(size // 2)   # centre the hit area on the zero-height groove
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background:    transparent;
                height:        0px;
                border:        none;
            }}
            QSlider::handle:horizontal {{
                background: transparent;
                border:     none;
                width:      {size}px;
                height:     {size}px;
                margin:     {side}px 0px;
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

    # ── Calibrated crop — baked from source image alpha padding ──────────────
    # These trim the transparent padding in ./Images/Value/ PNGs so the node
    # border sits flush against the visible content at any stored node size.
    # TOML [node.value] crop_* settings add on top for additional fine-tuning.
    _CAL_LEFT   = 0
    _CAL_RIGHT  = 15
    _CAL_TOP    = 0
    _CAL_BOTTOM = 7
    _CAL_PORT_Y = -12   # vertical offset from rect center to the input tip
    _CAL_PORT_X =  10   # horizontal offset added to the base -ox left-edge position

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _crop_left(self) -> float:
        import pretty_widgets.utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_left", 0))

    def _crop_right(self) -> float:
        import pretty_widgets.utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_right", 0))

    def _crop_top(self) -> float:
        import pretty_widgets.utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_top", 0))

    def _crop_bottom(self) -> float:
        import pretty_widgets.utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_bottom", 0))

    def _cropped_rect(self) -> QRectF:
        r  = self.rect()
        cl = self._CAL_LEFT   + self._crop_left()
        cr = self._CAL_RIGHT  + self._crop_right()
        ct = self._CAL_TOP    + self._crop_top()
        cb = self._CAL_BOTTOM + self._crop_bottom()
        return QRectF(r.left() + cl, r.top() + ct, r.width() - cl - cr, r.height() - ct - cb)

    def _slider_rect(self) -> QRectF:
        r = self._cropped_rect()
        return QRectF(r.left(), r.bottom() - _SLIDER_H, r.width(), _SLIDER_H)

    def _image_rect(self) -> QRectF:
        # Full node width and height above the slider — no button-zone reservation
        # (ValueNode has no buttons, so that 24px was dead space)
        r = self.rect()
        return QRectF(r.left(), r.top(), r.width(), r.height() - _SLIDER_H)

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

    # ── Z depth ───────────────────────────────────────────────────────────────

    _Z_FLOOR       = 100.0   # always in front of regular nodes
    _wire_clip     = False   # no border to tuck into — skip endpoint wire clipping
    _wire_at_port  = True    # wire terminates exactly at port position, no _INSIDE projection

    def setZValue(self, z: float) -> None:
        super().setZValue(max(z, self._Z_FLOOR))

    # ── Transparency guard ────────────────────────────────────────────────────

    def setBrush(self, brush):
        """Always transparent — NodeBehaviour bg-glow must not fill this node."""
        super().setBrush(Qt.NoBrush)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        self.paint_content(painter)
        painter.restore()

    def shape(self):
        path = QPainterPath()
        path.addRoundedRect(self._cropped_rect(), self.round_radius, self.round_radius)
        return path

    def boundingRect(self):
        return self._cropped_rect().adjusted(
            -Theme.nodeShadowMargin, -Theme.nodeShadowMargin,
             Theme.nodeShadowMargin,  Theme.nodeShadowMargin,
        )

    def paint_content(self, painter: QPainter) -> None:
        # Reposition slider proxy whenever the crop settings change
        crop = (self._crop_left(), self._crop_right(), self._crop_top(), self._crop_bottom())
        if crop != self._last_crop:
            self._last_crop = crop
            if hasattr(self, '_slider_proxy') and self._slider_proxy:
                self._slider_proxy.setGeometry(self._slider_rect())

        if not self._pixmap or self._pixmap.isNull():
            return

        clip = QPainterPath()
        clip.addRoundedRect(self._cropped_rect(), self.round_radius, self.round_radius)
        painter.setClipPath(clip)

        img_rect  = self._image_rect()
        scaled    = self._pixmap.size().scaled(img_rect.size().toSize(), Qt.KeepAspectRatioByExpanding)
        x         = img_rect.x() + (img_rect.width()  - scaled.width())  / 2
        y         = img_rect.y() + (img_rect.height() - scaled.height()) / 2
        dest      = QRectF(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(dest.toRect(), self._pixmap)

    # ── Resize ────────────────────────────────────────────────────────────────

    def setRect(self, rect):
        super().setRect(rect)
        # BaseNode.setRect gates _place_ports on output_ports — we have none,
        # so re-anchor the single W port manually.
        if self.input_ports:
            self._place_ports()
        if hasattr(self, '_slider_proxy') and self._slider_proxy:
            self._slider_proxy.setGeometry(self._slider_rect())

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if self._slider:
            try:
                self._slider.valueChanged.disconnect(self._seek)
            except RuntimeError:
                pass
        if hasattr(self, '_slider_proxy') and self._slider_proxy:
            self._slider_proxy.setWidget(None)
            self._slider_proxy.hide()
            self._slider_proxy = None
        if self._slider:
            self._slider.deleteLater()
        self._slider = None
        super()._prepare_for_removal()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ValueNode':
        return ValueNode(ValueNodeData.from_dict(data))
