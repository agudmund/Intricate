#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/NodeBehaviour.py
-The personality and ambient life of a node. Animations, character, soul.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random
from PySide6.QtCore import QVariantAnimation, QEasingCurve
from .Theme import Theme


# Pulse values resolved from Theme
PULSE_SCALE  = Theme.nodePulseScale
PULSE_MIN_MS = Theme.nodePulseMinMs
PULSE_MAX_MS = Theme.nodePulseMaxMs


class NodeBehaviour:
    """
    The character of a node. Not its function — its personality.

    Each node gets one NodeBehaviour at birth. It owns all ambient animation
    state that has nothing to do with structure or data — the breathing pulse,
    and whatever future behaviours nodes develop as citizens of Intricate.

    Current personality traits:
        Hover pulse — breathe in on hover, breathe out when the cursor leaves.
        Each node gets a randomised breath duration so they never synchronise,
        like blades of grass after a gust of wind.

    Future personality traits (parked, not forgotten):
        Idle drift         — gentle positional sway when untouched for a while
        Attention seeking  — subtle signal when a compatible wire gets close
        Pathfinding        — awareness of neighbours and canvas density

    Lifecycle contract:
        disconnect_all() MUST be called before the node leaves the scene.
        Qt's C++ side holds signal connections invisibly to Python's GC.
        Without explicit disconnection, the valueChanged → node.setScale
        connection keeps both the node and this behaviour alive after removal,
        causing the exact reference leak the HealthNode was built to detect.

        disconnect_all() is called by BaseNode._prepare_for_removal().
        It is safe to call multiple times — RuntimeError on an already-
        disconnected signal is caught and ignored.

        Do NOT call disconnect_all() from __del__ — by that point the C++
        animation object may already be invalid.
    """

    def __init__(self, node):
        """
        Attach behaviour to a node.

        Args:
            node: The BaseNode instance this behaviour belongs to.
                  Stored as a direct reference — this is safe because
                  disconnect_all() severs the Qt signal connections before
                  the node is destroyed, breaking the reference cycle.
        """
        self._node = node

        # ── Hover pulse ───────────────────────────────────────────────────────
        # Random duration so nodes never breathe in unison.
        self.pulse_anim = QVariantAnimation()
        self.pulse_anim.setDuration(random.randint(PULSE_MIN_MS, PULSE_MAX_MS))
        self.pulse_anim.setStartValue(1.0)
        self.pulse_anim.setEndValue(PULSE_SCALE)
        self.pulse_anim.setEasingCurve(QEasingCurve.InOutSine)

        # valueChanged drives the scale — connected now, disconnected on removal
        self.pulse_anim.valueChanged.connect(self._node.setScale)

        # finished drives the reverse — one connection, lives for the node's lifetime
        self.pulse_anim.finished.connect(self._on_pulse_finished)

    # ─────────────────────────────────────────────────────────────────────────
    # PERSONALITY — hover pulse
    # ─────────────────────────────────────────────────────────────────────────

    def on_hover_enter(self):
        """Breathe in — the node notices it's being looked at."""
        if self.pulse_anim.state() == QVariantAnimation.Stopped:
            self.pulse_anim.setDirection(QVariantAnimation.Forward)
            self.pulse_anim.start()

    def on_hover_leave(self):
        """
        Breathe out — the node settles back into itself.
        The reverse is handled by _on_pulse_finished so the breath
        completes naturally rather than snapping back.
        """
        pass

    def _on_pulse_finished(self):
        """When the forward breath completes, exhale back to rest."""
        if self.pulse_anim.direction() == QVariantAnimation.Forward:
            self.pulse_anim.setDirection(QVariantAnimation.Backward)
            self.pulse_anim.start()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def disconnect_all(self):
        """
        Sever all Qt signal connections and stop the animation.

        Called by BaseNode._prepare_for_removal() before scene departure.
        Must be called while the node is still in the scene and all Qt
        APIs are valid. Never call from __del__.

        Safe to call multiple times — already-disconnected signals raise
        RuntimeError which is caught and ignored.
        """
        try:
            self.pulse_anim.valueChanged.disconnect(self._node.setScale)
        except RuntimeError:
            pass
        try:
            self.pulse_anim.finished.disconnect(self._on_pulse_finished)
        except RuntimeError:
            pass
        self.pulse_anim.stop()
