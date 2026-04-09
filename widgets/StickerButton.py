#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - widgets/StickerButton.py StickerButton class
-A QPushButton that paints its icon with a dynamic radial shadow for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor


# Shadow tuning
SHADOW_DISTANCE = 4.0     # max pixel offset for the shadow
SHADOW_OPACITY  = 0.35    # shadow alpha multiplier
SHADOW_COLOR    = QColor(0, 0, 0, 90)  # tint applied to shadow copy


class StickerButton(QPushButton):
    """
    A frameless button that paints a sticker icon with a dynamic drop shadow.

    The shadow radiates outward from the window centre — creating a fake 3D
    lighting effect with a single overhead light at the centre of the screen.

    On press the icon shifts toward centre (into the surface) and the shadow
    disappears, giving physical button depth.
    """

    def __init__(self, pixmap: QPixmap, size: int, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._size = size
        self.setFixedSize(size, size)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")

    def _shadow_direction(self) -> QPointF:
        """Compute the normalised direction from window centre to this button's centre."""
        win = self.window()
        if not win:
            return QPointF(1.0, 1.0)  # default: bottom-right

        # Button centre in window coordinates
        btn_centre = self.mapTo(win, self.rect().center())
        # Window centre
        win_centre = QPointF(win.width() / 2.0, win.height() / 2.0)

        dx = btn_centre.x() - win_centre.x()
        dy = btn_centre.y() - win_centre.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1.0:
            return QPointF(0.0, 1.0)  # dead centre — shadow goes down
        return QPointF(dx / length, dy / length)

    def paintEvent(self, event) -> None:
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        sz = self._size
        direction = self._shadow_direction()
        pressed = self.isDown()

        if pressed:
            # Pressed — shift icon toward centre (opposite of shadow direction),
            # no shadow drawn. The button sinks into the surface.
            shift_x = -direction.x() * SHADOW_DISTANCE
            shift_y = -direction.y() * SHADOW_DISTANCE
            draw_rect = QRectF(shift_x, shift_y, sz, sz)
            painter.drawPixmap(draw_rect.toRect(), self._pixmap)
        else:
            # Normal — draw shadow offset outward, then icon at base position
            shadow_x = direction.x() * SHADOW_DISTANCE
            shadow_y = direction.y() * SHADOW_DISTANCE

            # Shadow: draw the pixmap with reduced opacity and darkened
            painter.setOpacity(SHADOW_OPACITY)
            shadow_rect = QRectF(shadow_x, shadow_y, sz, sz)
            painter.drawPixmap(shadow_rect.toRect(), self._pixmap)

            # Icon: draw at base position, full opacity
            painter.setOpacity(1.0)
            draw_rect = QRectF(0, 0, sz, sz)
            painter.drawPixmap(draw_rect.toRect(), self._pixmap)

        painter.end()
