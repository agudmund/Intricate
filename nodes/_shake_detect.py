#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/_shake_detect.py shake-to-delete helper
-The wiggle-sense every node shares, pulled out to a shared source of truth
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time as _time
from PySide6.QtCore import QPointF


_SHAKE_SAMPLE_INTERVAL = 0.03   # seconds between position samples
_SHAKE_WINDOW          = 0.40   # seconds of history to keep
_SHAKE_MIN_DELTA       = 8.0    # screen-px — ignore jitter smaller than this
_SHAKE_REVERSALS       = 3      # direction changes needed to trigger

_COOLDOWN_S            = 0.8
_cooldown_until: float = 0.0


def arm_cooldown() -> None:
    """Open the post-shake cooldown window. Subsequent shake attempts from
    any node are ignored until the window closes. Prevents cascade-deletes
    when Qt transfers the mouse grab to a neighbour after the shaken node
    is removed."""
    global _cooldown_until
    _cooldown_until = _time.monotonic() + _COOLDOWN_S


def is_cooling_down() -> bool:
    return _time.monotonic() < _cooldown_until


class ShakeDetector:
    """Composable shake-detect state.

    A host node creates one of these, arms it with press() on mouseDown,
    releases it with release() on mouseUp, and feeds scene-space position
    + current view zoom into track() on every mouseMoveEvent. When enough
    direction reversals accumulate in the window, the detector calls the
    `on_shake` callback once. Re-arms on the next press().

    Identical threshold math to BaseNode's inline implementation so shake
    feels the same regardless of which node type is being wiggled.
    """

    def __init__(self, on_shake):
        self._on_shake = on_shake
        self._samples: list = []
        self._triggered = False
        self._press_active = False

    def press(self) -> None:
        self._samples.clear()
        self._triggered = False
        self._press_active = True

    def release(self) -> None:
        self._press_active = False

    def track(self, scene_pos: QPointF, zoom: float) -> None:
        if is_cooling_down():
            return
        if not self._press_active:
            return
        if self._triggered:
            return
        now = _time.monotonic()
        if self._samples and (now - self._samples[-1][0]) < _SHAKE_SAMPLE_INTERVAL:
            return
        self._samples.append((now, QPointF(scene_pos)))
        cutoff = now - _SHAKE_WINDOW
        self._samples = [(t, p) for t, p in self._samples if t >= cutoff]
        if self._detect(zoom):
            self._triggered = True
            self._on_shake()

    def _detect(self, zoom: float) -> bool:
        """Count direction reversals on either axis — 3+ in the window = shake.
        Deltas converted to screen-space pixels so physical effort is
        zoom-independent."""
        pts = self._samples
        if len(pts) < 4:
            return False
        for axis in (0, 1):   # 0 = x, 1 = y
            reversals = 0
            prev_d = 0.0
            for i in range(1, len(pts)):
                d = (pts[i][1].x() - pts[i-1][1].x()) if axis == 0 \
                    else (pts[i][1].y() - pts[i-1][1].y())
                if abs(d * zoom) < _SHAKE_MIN_DELTA:
                    continue
                if prev_d != 0.0 and d * prev_d < 0:
                    reversals += 1
                prev_d = d
            if reversals >= _SHAKE_REVERSALS:
                return True
        return False
