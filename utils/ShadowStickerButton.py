#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/ShadowStickerButton.py ShadowStickerButton class
-A sticker-aesthetic QPushButton that casts a dynamic radial shadow for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor


# Shadow tuning
SHADOW_DISTANCE = 2.0     # max pixel offset for the shadow — subtle hint of depth
SHADOW_OPACITY  = 0.55    # shadow alpha multiplier
SHADOW_COLOR    = QColor(0, 0, 0, 90)  # tint applied to shadow copy


class ShadowStickerButton(QPushButton):
    """
    A frameless sticker-aesthetic button that casts a dynamic drop shadow.

    Distinct from StickerNode (flat, chromeless) — this variant carries
    depth. The shadow radiates outward from the window centre, giving a
    fake 3D lighting effect with a single overhead light at the centre of
    the screen. On press the icon shifts toward the shadow direction (into
    the surface) and the shadow disappears, giving physical button depth.

    The feed button in Intricate's sidebar is the baseline for the whole
    family — the reference implementation of this visual language across
    Intricate and future companion apps.
    """

    def __init__(self, pixmap: QPixmap, size: int, parent=None):
        super().__init__(parent)
        self._size = size
        # Pre-scale to 2× button size for crisp rendering on high-DPI displays.
        # A 1024px source scaled directly to 38px in drawPixmap loses detail;
        # LANCZOS-quality downscale to 2× then letting Qt halve it with
        # SmoothPixmapTransform gives much sharper results.
        dpr = 2.0
        px_size = int(size * dpr)
        self._pixmap = pixmap.scaled(px_size, px_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._pixmap.setDevicePixelRatio(dpr)
        self.setFixedSize(size, size)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("QPushButton { border: none; padding: 0px; background: transparent; }")

    def _build_shadow_pixmap(self) -> QPixmap:
        """Create a shadow silhouette from the sticker's alpha channel.

        Uses the sticker's shape (alpha) but fills with a dark tone —
        reads as a real shadow cast onto the surface rather than a
        transparent copy of the coloured icon.
        """
        sz = self._pixmap.size()
        # Start with the original pixmap (preserves alpha shape)
        shadow = QPixmap(sz)
        shadow.setDevicePixelRatio(self._pixmap.devicePixelRatio())
        shadow.fill(QColor(0, 0, 0, 0))

        p = QPainter(shadow)
        # Draw the sticker to capture its alpha channel
        p.drawPixmap(0, 0, self._pixmap)
        # Composite a dark fill over it using SourceAtop — replaces colour
        # but keeps the alpha channel intact
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        p.fillRect(0, 0, sz.width(), sz.height(), QColor(20, 18, 16))
        p.end()
        return shadow

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

        # Direction points from centre outward toward the button.
        # Shadow falls on the outside edge (same direction as the vector).
        # Pressed: icon shifts outward (away from light, into the surface).
        shadow_x = direction.x() * SHADOW_DISTANCE
        shadow_y = direction.y() * SHADOW_DISTANCE

        if pressed:
            # Pressed — icon shifts outward into where the shadow was, no shadow
            painter.drawPixmap(QPointF(shadow_x, shadow_y), self._pixmap)
        else:
            # Normal — shadow as a dark silhouette on the outside edge.
            # Build the shadow pixmap once and cache it — uses the sticker's
            # alpha channel as the shape but fills with a dark tone averaged
            # between the sticker body and the surface it sits on.
            if not hasattr(self, '_shadow_pix') or self._shadow_pix is None:
                self._shadow_pix = self._build_shadow_pixmap()

            painter.setOpacity(SHADOW_OPACITY)
            painter.drawPixmap(QPointF(shadow_x, shadow_y), self._shadow_pix)

            painter.setOpacity(1.0)
            painter.drawPixmap(QPointF(0, 0), self._pixmap)

        painter.end()
