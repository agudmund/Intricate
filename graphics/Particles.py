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
BURST_BASE_MS = 1200    # burst window at the reference count (8000 particles)
BURST_BASE_N  = 8000    # reference count — scales linearly above this
BURST_EASE    = 2.0     # exponent — >1 means fast start, decelerates outward

# ── Spiral tuning ─────────────────────────────────────────────────────────
SPIRAL_RADIUS = 576     # outer edge of the sunflower spiral
SPIRAL_JITTER = 30      # px of organic noise layered on each position
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))   # ≈ 137.5° in radians

# ── Global tick ───────────────────────────────────────────────────────────
_TICK_MS = 16           # ~60 fps — one timer drives every living particle

_alive: list = []
_tick_timer: QTimer | None = None


def _global_tick() -> None:
    global _alive
    now = time.monotonic() * 1000.0
    # Single-pass partition — O(n) instead of O(n²) list.remove() per dead
    still_alive = []
    for p in _alive:
        if p._update(now):
            still_alive.append(p)
    _alive = still_alive
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

    __slots__ = ('_scene', '_spawn_at', '_linger_end', '_fade_end', '_removed', '_item')

    def __init__(self, scene: QGraphicsScene, item: QGraphicsPixmapItem,
                 spawn_at_ms: float):
        self._scene       = scene
        self._spawn_at    = spawn_at_ms
        self._linger_end  = spawn_at_ms + LINGER_MS
        self._fade_end    = spawn_at_ms + LINGER_MS + FADE_MS
        self._removed     = False
        self._item        = item

    def _update(self, now_ms: float) -> bool:
        """Tick. Returns True while alive, False when done and removed."""
        try:
            if now_ms < self._spawn_at:
                return True

            if now_ms < self._linger_end:
                self._item.setOpacity(1.0)
                return True

            if now_ms < self._fade_end:
                t = (now_ms - self._linger_end) / FADE_MS
                self._item.setOpacity(max(0.0, 1.0 - t))
                return True

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
    # Load once at MAX_SIZE — no need to pull the full 1024px source
    # when particles never exceed 32px. If the icon file is already small
    # this is a no-op; if it's a 1k PNG this avoids scaling from 1024 → 32
    # on every size variant.
    raw = Theme.icon(icon_name or "heart.png", fallback_color=Theme.primaryBorder)
    base = raw.scaled(MAX_SIZE, MAX_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # Pre-scale every possible size from the small base
    size_cache = {MAX_SIZE: base}
    for s in range(MIN_SIZE, MAX_SIZE):
        size_cache[s] = base.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # Get the visible viewport rect in scene coordinates for clipping
    view_rect = None
    views = scene.views()
    if views:
        v = views[0]
        view_rect = v.mapToScene(v.viewport().rect()).boundingRect()

    # Pre-compute all positions and sizes in bulk — avoid per-item trig + random overhead
    cx, cy = center.x(), center.y()
    inv_total = 1.0 / max(count, 1)
    n = max(count - 1, 1)
    now = time.monotonic() * 1000.0

    _gauss   = random.gauss
    _sqrt    = math.sqrt
    _cos     = math.cos
    _sin     = math.sin
    _pow     = math.pow
    _clamp   = max
    _min     = min
    _int     = int
    _jitter  = SPIRAL_JITTER
    _radius  = SPIRAL_RADIUS
    _ga      = _GOLDEN_ANGLE
    _burst   = BURST_BASE_MS * max(1.0, count / BURST_BASE_N)
    _ease    = BURST_EASE
    _mean_sz = MEAN_SIZE
    _std_sz  = SIZE_STD_DEV

    vr_x0 = vr_y0 = vr_x1 = vr_y1 = 0.0
    do_clip = view_rect is not None
    if do_clip:
        vr_x0 = view_rect.x()
        vr_y0 = view_rect.y()
        vr_x1 = vr_x0 + view_rect.width()
        vr_y1 = vr_y0 + view_rect.height()

    batch = []
    # Turbulence — each particle inherits a fraction of the previous
    # particle's offset, creating correlated drift that reads as flow
    turb_x = 0.0
    turb_y = 0.0
    turb_carry = 0.4   # how much of the previous offset carries forward
    for i in range(count):
        # Position
        t      = (i + 0.5) * inv_total
        radius = _radius * _sqrt(t)
        angle  = i * _ga
        jx = _gauss(0, _jitter) + turb_x
        jy = _gauss(0, _jitter) + turb_y
        turb_x = jx * turb_carry
        turb_y = jy * turb_carry
        px = cx + radius * _cos(angle) + jx
        py = cy + radius * _sin(angle) + jy

        # Clip before creating any Qt objects
        if do_clip and (px < vr_x0 or px > vr_x1 or py < vr_y0 or py > vr_y1):
            continue

        # Size
        size = _clamp(MIN_SIZE, _min(MAX_SIZE, _int(_gauss(_mean_sz, _std_sz))))

        # Delay
        delay = _burst * _pow(i / n, _ease)

        batch.append((px - size * 0.5, py - size * 0.5, size, now + delay))

    # Create Qt items in one pass — all math is done
    for px, py, size, spawn_at in batch:
        item = QGraphicsPixmapItem(size_cache[size])
        item.setZValue(9999)
        item.setOpacity(0.0)
        item.setPos(px, py)
        scene.addItem(item)
        _alive.append(_FadingParticle(scene, item, spawn_at))

    _ensure_ticking()
