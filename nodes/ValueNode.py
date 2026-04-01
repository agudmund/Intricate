#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ValueNode.py ValueNode class
-Transparent image-sequence node with PrettySlider scrubber, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re
import time as _time
from pathlib import Path

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from nodes.BaseNode import BaseNode
from data.ValueNodeData import ValueNodeData
from graphics.Theme import Theme
import widgets.PrettySlider as pretty_slider


_IMAGES_DIR = Path(__file__).resolve().parent.parent / "Images" / "Value"
_SLIDER_H   = 32   # tall enough for the 28px handle icon + 2px each side
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

# Cooldown prevents cascade-deletes when the mouse grab transfers after removal
_SHAKE_COOLDOWN_S   = 0.8
_shake_cooldown_until: float = 0.0   # module-level, shared across all ValueNode instances


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
        self._shake_press_active: bool = False
        self._last_crop: tuple = (self._crop_left(), self._crop_right(), self._crop_top(), self._crop_bottom())

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
        """One input port on the W (left-center) edge. No output ports."""
        from nodes.Port import Port
        port = Port(self, is_output=False)
        self.input_ports  = [port]
        self.output_ports = []
        self.input_port   = port
        self.output_port  = None
        self._place_ports()
        port.hide()

    def _place_ports(self) -> None:
        if not self.input_ports:
            return
        import utils.settings as _s
        r      = self.rect()
        ox     = 10
        y_off  = float(_s.get_nested("node", "value", "input_port_y_offset", 0))
        x_off  = float(_s.get_nested("node", "value", "input_port_x_offset", 0))
        self.input_ports[0].setPos(-ox + self._CAL_PORT_X + x_off, r.height() / 2 + self._CAL_PORT_Y + y_off)

    def closest_input_port(self, scene_pos):
        return self.input_ports[0]

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
        import utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_left", 0))

    def _crop_right(self) -> float:
        import utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_right", 0))

    def _crop_top(self) -> float:
        import utils.settings as _s
        return float(_s.get_nested("node", "value", "crop_top", 0))

    def _crop_bottom(self) -> float:
        import utils.settings as _s
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

    # ── Mouse press/release guards ────────────────────────────────────────────

    def mousePressEvent(self, event):
        self._shake_press_active = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._shake_press_active = False
        super().mouseReleaseEvent(event)
        if getattr(self, '_pending_shake_delete', False):
            self._pending_shake_delete = False
            scene = self.scene()
            if scene:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: scene.removeItem(self))

    # ── Shake tracking (always active, with or without connections) ───────────

    def _track_shake(self) -> None:
        """Same as BaseNode but without the `not self.connections` early-out.
        Gated on _shake_press_active so stray move events after another node's
        removal can't trigger shake on this node without a proper press first.
        Also gated on a module-level cooldown that blocks cascade-deletes when
        Qt transfers the mouse grab after the previous ValueNode was removed."""
        global _shake_cooldown_until
        if _time.monotonic() < _shake_cooldown_until:
            return
        if not self._shake_press_active:
            return
        if self._shake_triggered:
            return
        now = _time.monotonic()
        if self._shake_samples and (now - self._shake_samples[-1][0]) < self._SHAKE_SAMPLE_INTERVAL:
            return
        from PySide6.QtCore import QPointF as _QPointF
        self._shake_samples.append((now, _QPointF(self.scenePos())))
        cutoff = now - self._SHAKE_WINDOW
        self._shake_samples = [(t, p) for t, p in self._shake_samples if t >= cutoff]
        if self._detect_shake():
            self._shake_triggered = True
            self._shake_detach()

    # ── Shake-to-delete (unconnected) ────────────────────────────────────────

    def _shake_detach(self) -> None:
        """When unconnected, a shake deletes the node with a heart burst."""
        if self.connections:
            super()._shake_detach()
            return
        scene = self.scene()
        if not scene:
            return
        global _shake_cooldown_until
        _shake_cooldown_until = _time.monotonic() + _SHAKE_COOLDOWN_S
        from graphics.Particles import sprinkle
        sprinkle(scene, self.mapToScene(self.rect().center()), count=162)
        # Do NOT call setVisible(False) here — Qt silently ungrabs the mouse
        # when an item is hidden, so mouseReleaseEvent never fires and
        # _pending_shake_delete is never processed, leaving an invisible
        # Z=100 node in the scene that intercepts every subsequent click.
        # The hearts give sufficient visual feedback; the border is gone
        # the moment the user releases the mouse.
        self._pending_shake_delete = True

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
