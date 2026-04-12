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
from PySide6.QtGui import QPixmap, QColor

from pretty_widgets.graphics.Theme import Theme


# ── Size tuning ───────────────────────────────────────────────────────────
MEAN_SIZE    = 18       # most particles around this size
SIZE_STD_DEV = 8        # natural variation
MIN_SIZE     = 10
MAX_SIZE     = 32

# ── Lifetime tuning ───────────────────────────────────────────────────────
LINGER_MS    = 600      # fully visible after spawning before fade begins
FADE_MS      = 800      # fade-out duration per particle

# ── Burst timing ──────────────────────────────────────────────────────────
BURST_BASE_MS = 2000    # burst window at the reference count (16000 particles)

# ── Icon cache (resolved once per app run) ────────────────────────────────
_icon_base_cache: dict[str, QPixmap] = {}   # icon_name → MAX_SIZE base pixmap
_icon_size_cache: dict[str, dict[int, QPixmap]] = {}  # icon_name → {size: pixmap}
BURST_BASE_N  = 16000   # reference count — scales linearly above this
BURST_EASE    = 1.4     # exponent — >1 means fast start, decelerates outward

# ── Spiral tuning ─────────────────────────────────────────────────────────
SPIRAL_RADIUS = 576     # outer edge of the sunflower spiral
SPIRAL_JITTER = 30      # px of organic noise layered on each position
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))   # ≈ 137.5° in radians

# ── Global tick ───────────────────────────────────────────────────────────
_TICK_MS = 16           # ~60 fps — one timer drives every living particle

# ── Shake mode toggle ────────────────────────────────────────────────────
# "sprinkle" = original sunflower burst, "orbital" = torus knot swarm
shake_mode: str = "sprinkle"

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
            if self._removed:
                return False

            if now_ms < self._spawn_at:
                return True

            if now_ms < self._linger_end:
                self._item.setOpacity(1.0)
                return True

            if now_ms < self._fade_end:
                t = (now_ms - self._linger_end) / FADE_MS
                self._item.setOpacity(max(0.0, 1.0 - t))
                return True

            self._finish()
            return False

        except RuntimeError:
            self._item = None
            self._scene = None
            return False

    def _finish(self) -> None:
        """Remove item from scene and release references."""
        if self._removed:
            return
        self._removed = True
        try:
            if self._item is not None and self._item.scene():
                self._scene.removeItem(self._item)
        except RuntimeError:
            pass
        self._item  = None
        self._scene = None


def sprinkle(scene: QGraphicsScene, center: QPointF,
             count: int = 6, icon_name: str | None = None,
             seed: int | None = None,
             density_falloff: str = "uniform",
             distance: float = SPIRAL_RADIUS) -> None:
    """
    Spawn a burst of fading particles around a scene position.

    All particles are registered immediately; a single global QTimer drives
    every opacity update — no per-particle timers.
    """
    # Resolve the icon once per app run — Theme.icon() hits the file system
    # and logs on every cache miss. For the particle simulator every
    # microsecond counts, so we skip both the lookup and the log after the
    # first call by caching the scaled pixmaps at module level.
    key = icon_name or "heart.png"
    if key not in _icon_size_cache:
        raw = Theme.icon(key, fallback_color=Theme.primaryBorder)
        base = raw.scaled(MAX_SIZE, MAX_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _icon_base_cache[key] = base
        sc = {MAX_SIZE: base}
        for s in range(MIN_SIZE, MAX_SIZE):
            sc[s] = base.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _icon_size_cache[key] = sc
    size_cache = _icon_size_cache[key]

    # Seed for reproducible scatters
    if seed is not None:
        random.seed(seed)

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
    _radius  = distance
    _ga      = _GOLDEN_ANGLE
    _burst   = BURST_BASE_MS * max(1.0, count / BURST_BASE_N)
    _ease    = BURST_EASE
    _mean_sz = MEAN_SIZE
    _std_sz  = SIZE_STD_DEV

    batch = []
    # Turbulence — each particle inherits a fraction of the previous
    # particle's offset, creating correlated drift that reads as flow
    turb_x = 0.0
    turb_y = 0.0
    turb_carry = 0.4   # how much of the previous offset carries forward
    for i in range(count):
        # Position — density falloff modulates radial distribution
        t = (i + 0.5) * inv_total
        if density_falloff == "center":
            t = t * t                  # bias toward center (small radius)
        elif density_falloff == "edge":
            t = 1.0 - (1.0 - t) ** 2  # bias toward edge (large radius)
        radius = _radius * _sqrt(t)
        angle  = i * _ga
        jx = _gauss(0, _jitter) + turb_x
        jy = _gauss(0, _jitter) + turb_y
        turb_x = jx * turb_carry
        turb_y = jy * turb_carry
        px = cx + radius * _cos(angle) + jx
        py = cy + radius * _sin(angle) + jy

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


# ── Orbital torus knot burst ─────────────────────────────────────────────

ORBITAL_COUNT     = 8000    # particle count for the orbital swarm
ORBITAL_SCALE     = 6.0     # swarm coordinates → scene pixels
ORBITAL_LIVE_MS   = 2800    # how long the swarm animates before fading
ORBITAL_FADE_MS   = 600     # fade-out after the live phase
ORBITAL_ICON_SIZE = 14      # pixel size of each PNG particle

_orbital_bursts: list = []  # active _OrbitalBurst instances


class _OrbitalBurst:
    """Manages a swarm of PNG particles driven by OrbitalSwarm, then fades them out."""

    __slots__ = ('_scene', '_swarm', '_items', '_cx', '_cy', '_born',
                 '_fade_start', '_fade_end', '_removed', '_scale')

    def __init__(self, scene: QGraphicsScene, center: QPointF, count: int,
                 icon_name: str | None = None, lerp_rate: float = 0.1,
                 speed: float = 0.7, scale: float = ORBITAL_SCALE):
        from utils.OrbitalMotion import OrbitalSwarm

        self._scene = scene
        self._cx    = center.x()
        self._cy    = center.y()
        self._scale = scale
        self._born  = time.monotonic() * 1000.0
        self._fade_start = self._born + ORBITAL_LIVE_MS
        self._fade_end   = self._fade_start + ORBITAL_FADE_MS
        self._removed = False

        self._swarm = OrbitalSwarm(
            count=count, rings=21.79, radius=10.0,
            spread=69.0, twist=0.6, speed=speed,
            morph=1.0, lerp_rate=lerp_rate,
        )

        # Resolve the icon pixmap — reuse the sprinkle icon cache
        key = icon_name or "heart.png"
        if key not in _icon_size_cache:
            raw = Theme.icon(key, fallback_color=Theme.primaryBorder)
            base = raw.scaled(MAX_SIZE, MAX_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _icon_base_cache[key] = base
            sc = {MAX_SIZE: base}
            for s in range(MIN_SIZE, MAX_SIZE):
                sc[s] = base.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _icon_size_cache[key] = sc
        pixmap = _icon_size_cache[key].get(
            ORBITAL_ICON_SIZE,
            _icon_base_cache[key].scaled(ORBITAL_ICON_SIZE, ORBITAL_ICON_SIZE,
                                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

        # Create PNG particle items — all share the same pixmap
        self._items = []
        for _ in range(count):
            item = QGraphicsPixmapItem(pixmap)
            item.setZValue(9999)
            item.setOpacity(0.0)
            scene.addItem(item)
            self._items.append(item)

    def _update(self, now_ms: float) -> bool:
        """Tick — advance swarm, reposition particles, handle fade. Returns True while alive."""
        try:
            if self._removed:
                return False

            # Advance the pure-math swarm
            self._swarm.tick(_TICK_MS / 1000.0)

            # Fade multiplier
            if now_ms >= self._fade_end:
                self._cleanup()
                return False
            elif now_ms >= self._fade_start:
                fade = 1.0 - (now_ms - self._fade_start) / ORBITAL_FADE_MS
            elif now_ms < self._born + 200:
                # Quick fade-in over 200ms
                fade = (now_ms - self._born) / 200.0
            else:
                fade = 1.0

            cx, cy, scale = self._cx, self._cy, self._scale
            half = ORBITAL_ICON_SIZE * 0.5
            items = self._items

            for i in range(len(items)):
                x, y, z, h, s, l = self._swarm.particle(i)
                # Depth → opacity (nearer = brighter)
                depth_factor = 0.3 + 0.7 * (z / (self._swarm.radius * 5.0) + 0.5)
                depth_factor = max(0.1, min(1.0, depth_factor))

                items[i].setPos(cx + x * scale - half, cy + y * scale - half)
                items[i].setOpacity(fade * depth_factor)

            return True

        except RuntimeError:
            self._cleanup()
            return False

    def _cleanup(self):
        if self._removed:
            return
        self._removed = True
        for item in self._items:
            try:
                if item.scene():
                    self._scene.removeItem(item)
            except RuntimeError:
                pass
        self._items.clear()
        self._swarm = None
        self._scene = None


def _orbital_tick() -> None:
    """Drive all active orbital bursts from the same global timer."""
    global _orbital_bursts
    now = time.monotonic() * 1000.0
    _orbital_bursts = [b for b in _orbital_bursts if b._update(now)]
    if not _orbital_bursts and _orbital_tick_timer is not None:
        _orbital_tick_timer.stop()


def orbital_burst(scene: QGraphicsScene, center: QPointF,
                  count: int = ORBITAL_COUNT,
                  icon_name: str | None = None,
                  stiffness: float = 0.1,
                  speed: float = 0.7,
                  distance: float = ORBITAL_SCALE) -> None:
    """Spawn an orbital torus knot particle swarm at a scene position."""
    burst = _OrbitalBurst(scene, center, count, icon_name=icon_name,
                          lerp_rate=stiffness, speed=speed, scale=distance)
    _orbital_bursts.append(burst)
    _ensure_orbital_ticking()


# ── Orbital tick integration ─────────────────────────────────────────────
_orbital_tick_timer: QTimer | None = None


def _ensure_orbital_ticking() -> None:
    global _orbital_tick_timer
    if _orbital_tick_timer is None:
        _orbital_tick_timer = QTimer()
        _orbital_tick_timer.setInterval(_TICK_MS)
        _orbital_tick_timer.timeout.connect(_orbital_tick)
    if not _orbital_tick_timer.isActive():
        _orbital_tick_timer.start()


def flush_scene(scene: QGraphicsScene) -> None:
    """Immediately remove all living particles belonging to a scene.

    Call this before tearing down a scene so the global tick timers don't
    dereference stale C++ pointers on the next 16 ms tick.
    """
    global _alive, _orbital_bursts

    _alive = [p for p in _alive if not _flush_particle(p, scene)]
    if not _alive and _tick_timer is not None:
        _tick_timer.stop()

    remaining = []
    for burst in _orbital_bursts:
        if burst._scene is scene:
            burst._cleanup()
        else:
            remaining.append(burst)
    _orbital_bursts = remaining
    if not _orbital_bursts and _orbital_tick_timer is not None:
        _orbital_tick_timer.stop()


def _flush_particle(p: _FadingParticle, scene: QGraphicsScene) -> bool:
    """If particle belongs to the given scene, kill it. Returns True if killed."""
    if p._scene is not scene:
        return False
    p._finish()
    return True
