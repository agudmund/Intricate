#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/NodeBehaviour.py NodeBehaviour class
-The personality and ambient life of a node. Animations, character, soul for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import random
import warnings
from PySide6.QtCore import QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QBrush
from graphics.Theme import Theme


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

        # ── Background glow ───────────────────────────────────────────────────
        # Blends the node's own resting brush color toward the accent on hover/select.
        # _bg_base is captured lazily on first use — after subclass __init__ has set
        # its own brush — so HealthNode, ClaudeNode etc. all return to their own color.
        self._bg_base:    QColor | None = None   # set on first animation
        self._current_bg: QColor | None = None   # tracks live animated value
        self.bg_anim = QVariantAnimation()
        self.bg_anim.setEasingCurve(QEasingCurve.InOutSine)
        self.bg_anim.valueChanged.connect(self._on_bg_changed)

    # ─────────────────────────────────────────────────────────────────────────
    # PERSONALITY — hover pulse
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # COLOR HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _blend(a, b, t: float) -> QColor:
        """Linear interpolate between two colors (hex str or QColor) at factor t."""
        if isinstance(a, str): a = QColor(a)
        if isinstance(b, str): b = QColor(b)
        return QColor(
            int(a.red()   + (b.red()   - a.red())   * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue()  + (b.blue()  - a.blue())  * t),
        )

    def _ensure_base(self) -> QColor:
        """Return the node's resting brush color, capturing it on first call."""
        if self._bg_base is None:
            self._bg_base    = QColor(self._node.brush().color())
            self._current_bg = QColor(self._bg_base)
        return self._bg_base

    def _bg_normal(self)   -> QColor: return QColor(self._ensure_base())
    def _bg_hover(self)    -> QColor: return self._blend(self._ensure_base(), Theme.primaryBorder, 0.015)
    def _bg_selected(self) -> QColor: return self._blend(self._ensure_base(), Theme.primaryBorder, 0.03)

    def _animate_bg_to(self, target: QColor, duration: int) -> None:
        self._ensure_base()   # guarantee _current_bg is initialised before use
        self.bg_anim.stop()
        self.bg_anim.setStartValue(QColor(self._current_bg))
        self.bg_anim.setEndValue(target)
        self.bg_anim.setDuration(duration)
        self.bg_anim.start()

    def _on_bg_changed(self, color: QColor) -> None:
        self._current_bg = color
        try:
            self._node.setBrush(QBrush(color))
        except RuntimeError:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # PERSONALITY — hover pulse + background glow
    # ─────────────────────────────────────────────────────────────────────────

    def on_hover_enter(self):
        """Breathe in — scale swells, background warms toward the accent."""
        if self.pulse_anim.state() == QVariantAnimation.Stopped:
            self.pulse_anim.setDirection(QVariantAnimation.Forward)
            self.pulse_anim.start()
        self._animate_bg_to(self._bg_hover(), 320)

    def on_hover_leave(self):
        """
        Breathe out — scale settles via _on_pulse_finished.
        Background returns to selected tint if selected, otherwise to normal.
        """
        target = self._bg_selected() if self._node.isSelected() else self._bg_normal()
        self._animate_bg_to(target, 450)

    def on_selected(self, is_selected: bool) -> None:
        """Background shifts to the selected tint (or back to normal on deselect)."""
        target = self._bg_selected() if is_selected else self._bg_normal()
        self._animate_bg_to(target, 180)

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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.pulse_anim.valueChanged.disconnect(self._node.setScale)
            except RuntimeError:
                pass
            try:
                self.pulse_anim.finished.disconnect(self._on_pulse_finished)
            except RuntimeError:
                pass
            try:
                self.bg_anim.valueChanged.disconnect(self._on_bg_changed)
            except RuntimeError:
                pass
        self.pulse_anim.stop()
        self.bg_anim.stop()
