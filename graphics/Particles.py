#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Particles.py particle sprinkle
-Gaussian-clustered fading pixmaps for visual celebration for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPixmap

from graphics.Theme import Theme


# ── Size tuning ───────────────────────────────────────────────────────────
MEAN_SIZE    = 18       # most particles around this size
SIZE_STD_DEV = 8        # natural variation
MIN_SIZE     = 10
MAX_SIZE     = 32

# ── Fade tuning ───────────────────────────────────────────────────────────
LINGER_MS    = 600      # how long the particle is fully visible before fading
FADE_STEPS   = 12       # number of opacity steps during fade-out
FADE_MS      = 25       # ms between fade steps
STAGGER_MS   = 90       # ms between each particle spawn in a burst


_alive: set = set()   # prevent GC until fade completes


class _FadingParticle:
    """One particle — placed, shown, faded, removed. Fire and forget."""

    def __init__(self, scene: QGraphicsScene, center: QPointF, pixmap: QPixmap):
        _alive.add(self)
        size = max(MIN_SIZE, min(MAX_SIZE, int(random.gauss(MEAN_SIZE, SIZE_STD_DEV))))
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self._item = QGraphicsPixmapItem(scaled)
        self._item.setZValue(9999)   # always on top

        # Gaussian scatter around the center — 83% cluster tight, 17% wander
        if random.random() < 0.83:
            ox = random.gauss(0, 28)
            oy = random.gauss(0, 28)
        else:
            ox = random.uniform(-80, 80)
            oy = random.uniform(-80, 80)

        self._item.setPos(center.x() + ox - size / 2,
                          center.y() + oy - size / 2)
        scene.addItem(self._item)
        self._scene = scene

        # Linger fully visible, then fade
        self._step = 0
        self._fade_timer = QTimer()
        self._fade_timer.setInterval(FADE_MS)
        self._fade_timer.timeout.connect(self._tick)

        self._linger = QTimer()
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(self._fade_timer.start)
        self._linger.start(LINGER_MS)

    def _tick(self) -> None:
        self._step += 1
        opacity = max(0.0, 1.0 - self._step / FADE_STEPS)
        try:
            if self._item.scene():
                self._item.setOpacity(opacity)
            if self._step >= FADE_STEPS:
                self._fade_timer.stop()
                if self._item.scene():
                    self._scene.removeItem(self._item)
                _alive.discard(self)
        except RuntimeError:
            self._fade_timer.stop()
            _alive.discard(self)


def sprinkle(scene: QGraphicsScene, center: QPointF,
             count: int = 6, icon_name: str | None = None) -> None:
    """
    Spawn a burst of fading particles around a scene position.

    Each particle is staggered by STAGGER_MS so they cascade rather
    than pop in all at once.  Uses Theme.icon for the pixmap — defaults
    to the iconic.png fallback circle if no icon is specified.
    """
    pixmap = Theme.icon(icon_name or "bezier_icon.png", fallback_color=Theme.primaryBorder)

    for i in range(count):
        QTimer.singleShot(i * STAGGER_MS,
                          lambda c=center, p=pixmap: _FadingParticle(scene, c, p))
