#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Particles.py particle sprinkle
-Gaussian-clustered fading pixmaps for visual celebration for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
import random
import time
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPixmap

from graphics.Theme import Theme


# ── Size tuning ───────────────────────────────────────────────────────────
MEAN_SIZE    = 18       # most particles around this size
SIZE_STD_DEV = 8        # natural variation
MIN_SIZE     = 10
MAX_SIZE     = 32

# ── Lifetime tuning ───────────────────────────────────────────────────────
LINGER_MS    = 150      # fully visible after spawning before fade begins
FADE_MS      = 300      # fade-out duration per particle

# ── Burst timing ──────────────────────────────────────────────────────────
BURST_MS     = 2000     # total window from first to last particle spawn
BURST_EASE   = 2.0      # exponent — >1 means fast start, decelerates outward

# ── Spiral tuning ─────────────────────────────────────────────────────────
SPIRAL_RADIUS = 480     # outer edge of the sunflower spiral
SPIRAL_JITTER = 30      # px of organic noise layered on each position
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))   # ≈ 137.5° in radians

# ── Global tick ───────────────────────────────────────────────────────────
_TICK_MS = 16           # ~60 fps — one timer drives every living particle

_alive: list = []
_tick_timer: QTimer | None = None


def _global_tick() -> None:
    now  = time.monotonic() * 1000.0
    dead = [p for p in _alive if not p._update(now)]
    for p in dead:
        _alive.remove(p)
    if not _alive and _tick_timer is not None:
        _tick_timer.stop()


def _ensure_ticking() -> None:
    global _tick_timer
    if _tick_timer is None:
        _tick_timer = QTimer()
        _tick_timer.setInterval(_TICK_MS)
        _tick_timer.timeout.connect(_global_tick)
    if not _tick_timer.isActive():
        _tick_timer.start()


class _FadingParticle:
    """One particle — timestamped spawn, linger, fade. No per-particle timers."""

    def __init__(self, scene: QGraphicsScene, center: QPointF, pixmap: QPixmap,
                 index: int, total: int, spawn_delay_ms: float):
        now               = time.monotonic() * 1000.0
        self._scene       = scene
        self._spawn_at    = now + spawn_delay_ms
        self._linger_end  = self._spawn_at + LINGER_MS
        self._fade_end    = self._linger_end + FADE_MS
        self._removed     = False

        size   = max(MIN_SIZE, min(MAX_SIZE, int(random.gauss(MEAN_SIZE, SIZE_STD_DEV))))
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self._item = QGraphicsPixmapItem(scaled)
        self._item.setZValue(9999)
        self._item.setOpacity(0.0)   # invisible until spawn_at

        # Sunflower / phyllotaxis spiral position
        t      = (index + 0.5) / max(total, 1)
        radius = SPIRAL_RADIUS * math.sqrt(t)
        angle  = index * _GOLDEN_ANGLE
        ox     = radius * math.cos(angle) + random.gauss(0, SPIRAL_JITTER)
        oy     = radius * math.sin(angle) + random.gauss(0, SPIRAL_JITTER)

        self._item.setPos(center.x() + ox - size / 2,
                          center.y() + oy - size / 2)
        scene.addItem(self._item)

    def _update(self, now_ms: float) -> bool:
        """Tick. Returns True while alive, False when done and removed."""
        try:
            if now_ms < self._spawn_at:
                return True                          # not yet visible

            if now_ms < self._linger_end:
                self._item.setOpacity(1.0)
                return True

            if now_ms < self._fade_end:
                t = (now_ms - self._linger_end) / FADE_MS
                self._item.setOpacity(max(0.0, 1.0 - t))
                return True

            # Lifetime over
            if not self._removed:
                self._removed = True
                if self._item.scene():
                    self._scene.removeItem(self._item)
            return False

        except RuntimeError:
            return False


def sprinkle(scene: QGraphicsScene, center: QPointF,
             count: int = 6, icon_name: str | None = None) -> None:
    """
    Spawn a burst of fading particles around a scene position.

    All particles are registered immediately; a single global QTimer drives
    every opacity update — no per-particle timers.
    """
    pixmap = Theme.icon(icon_name or "heart.png", fallback_color=Theme.primaryBorder)

    n = max(count - 1, 1)
    for i in range(count):
        t     = i / n
        delay = BURST_MS * math.pow(t, BURST_EASE)
        _alive.append(_FadingParticle(scene, center, pixmap, i, count, delay))

    _ensure_ticking()
