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
from pretty_widgets.graphics.Theme import Theme


# Pulse values resolved from Theme
PULSE_SCALE  = Theme.nodePulseScale
PULSE_MIN_MS = Theme.nodePulseMinMs
PULSE_MAX_MS = Theme.nodePulseMaxMs

# Aerial-view gate — minimum on-screen node dimension (viewport pixels)
# below which hover pulse + bg animations suppress themselves.  The
# 1.018 scale factor produces a ~1 px visual delta at 60 px — anything
# smaller is imperceptible and the animation is pure cost.  Matches the
# 60 px landmark used by the VideoNode tiny-render pause.  Above this
# threshold, pulse runs full fat for the signature gust-of-wind effect
# (see memory: project_pulse_vibrance_commitment).
_PULSE_MIN_ON_SCREEN_PX = 60.0

# Pulse-damping reference size — node dimension at and below which
# PULSE_SCALE is honoured verbatim.  Above this size, the effective
# pulse scale shrinks so the absolute outward pixel-expansion at the
# largest axis stays roughly constant rather than growing linearly
# with node size.
#
# Why: with a flat PULSE_SCALE = 1.018, a 300-px node grows ~5 px
# outward (subtle, lovely), but a 2000-px node grows ~36 px — enough
# to displace the bottom-right resize handle visibly during hover and
# make it physically hard to track and grab.  The dampening keeps the
# pulse signature unchanged for regular-sized nodes (the canonical
# gust-of-wind aesthetic) and only diminishes the swell on huuuge
# nodes where the constant-percentage scale stops feeling proportional.
#
# Math: target absolute growth = (PULSE_SCALE - 1.0) × reference_px.
# At the reference size, effective_scale = PULSE_SCALE (full pulse).
# Above reference, effective_scale = 1.0 + target_growth / largest_dim,
# so largest_dim × (effective_scale - 1.0) = target_growth always.
_PULSE_DAMPING_REFERENCE_PX = 500.0


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

        # valueChanged drives the scale — connected now, disconnected on removal.
        # Routed through _on_pulse_value so we can early-return during a bulk
        # remove burst (scene._bulk_removing > 0). setScale() invalidates the
        # peer's paint region; skipping it during the burst removes one more
        # vector into the peer-paint-during-burst crash class.
        self.pulse_anim.valueChanged.connect(self._on_pulse_value)

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
        """Linear interpolate between two colors (hex str or QColor) at factor t.

        Preserves the first colour's alpha — hover and selection tints should
        shift hue subtly, not flip the node between translucent and opaque.
        Without this, a node with an alpha<255 brush visibly flashes to full
        opacity on hover because QColor(r, g, b) defaults alpha to 255,
        which reads as a larger lightness shift than the 0.015/0.03 blend
        itself.
        """
        if isinstance(a, str): a = QColor(a)
        if isinstance(b, str): b = QColor(b)
        return QColor(
            int(a.red()   + (b.red()   - a.red())   * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue()  + (b.blue()  - a.blue())  * t),
            a.alpha(),
        )

    def _ensure_base(self) -> QColor:
        """Return the node's resting brush color, capturing it on first call."""
        if self._bg_base is None:
            if self._node is None:
                self._bg_base = QColor(Theme.windowBg)
                self._current_bg = QColor(self._bg_base)
            else:
                self._bg_base    = QColor(self._node.brush().color())
                self._current_bg = QColor(self._bg_base)
        return self._bg_base

    def _bg_normal(self)   -> QColor: return QColor(self._ensure_base())
    def _bg_hover(self)    -> QColor: return self._blend(self._ensure_base(), Theme.primaryBorder, 0.015)
    def _bg_selected(self) -> QColor: return self._blend(self._ensure_base(), Theme.primaryBorder, 0.03)

    def _should_pulse(self) -> bool:
        """Aerial-view gate: skip pulse / bg animations when the node is
        too small on screen for the effect to read.  Pulse animations are
        a signature aesthetic at street-level zoom but pure CPU cost when
        the scale delta is smaller than a pixel.  Evaluated per-trigger,
        not per-tick — cheap."""
        if self._node is None:
            return False
        try:
            scene = self._node.scene()
        except RuntimeError:
            return False
        if scene is None:
            return False
        views = scene.views()
        if not views:
            # No view context yet (e.g. during construction).  Default to
            # active — the gate only exists to silence aerial views, not
            # to suppress default behaviour when the view isn't wired.
            return True
        zoom = getattr(views[0], 'current_zoom', 1.0)
        try:
            rect = self._node.rect()
        except (RuntimeError, AttributeError):
            return True
        smaller_dim = min(rect.width(), rect.height())
        return smaller_dim * zoom >= _PULSE_MIN_ON_SCREEN_PX

    def _compute_effective_pulse_scale(self) -> float:
        """Peak hover-pulse scale, dampened by node size.

        For default-sized nodes (largest dimension ≤ _PULSE_DAMPING_REFERENCE_PX)
        returns PULSE_SCALE verbatim — the canonical gust-of-wind aesthetic is
        untouched at the sizes nodes most often inhabit.  For larger nodes the
        scale shrinks toward 1.0 so the absolute outward pixel-expansion at the
        largest axis stays roughly constant rather than growing linearly with
        node size.

        Without this, a 2000-px node grows ~36 px outward at peak pulse —
        enough to displace the bottom-right resize handle visibly during
        hover and make it physically hard to track and grab.

        Re-evaluated per hover-enter (cheap), so live-resized nodes pick
        up the new dampening on the next breath without bookkeeping.
        """
        if self._node is None:
            return PULSE_SCALE
        try:
            rect = self._node.rect()
        except (RuntimeError, AttributeError):
            return PULSE_SCALE
        largest_dim = max(rect.width(), rect.height())
        if largest_dim <= _PULSE_DAMPING_REFERENCE_PX:
            return PULSE_SCALE
        target_growth = (PULSE_SCALE - 1.0) * _PULSE_DAMPING_REFERENCE_PX
        return 1.0 + target_growth / largest_dim

    def _animate_bg_to(self, target: QColor, duration: int) -> None:
        self._ensure_base()   # guarantee _current_bg is initialised before use
        # Aerial view: snap directly to the target colour without
        # animating.  Preserves correctness (selection colour still
        # updates, hover highlight still settles to the right resting
        # tone) while dropping the 60Hz tick cost.  _on_bg_changed's
        # _bulk_removing guard still applies via the explicit call.
        if not self._should_pulse():
            self.bg_anim.stop()
            self._on_bg_changed(target)
            return
        self.bg_anim.stop()
        self.bg_anim.setStartValue(QColor(self._current_bg))
        self.bg_anim.setEndValue(target)
        self.bg_anim.setDuration(duration)
        self.bg_anim.start()

    def _on_bg_changed(self, color: QColor) -> None:
        self._current_bg = color
        if self._node is None:
            return
        # Peer quiescence: during a bulk-remove OR bulk-add burst the
        # surrounding event loop is saturated. A setBrush() here would
        # schedule a repaint that can land after a peer's C++ side has
        # been freed (remove case), or cascade paint invalidation across
        # existing peers during a bulk import (add case — see
        # Scene.import_session comment for the 89-node hang). Skip the
        # mutation either way — the final target colour still resolves
        # correctly once the burst ends; we just drop interim frames.
        try:
            sc = self._node.scene()
            if sc is not None and (
                getattr(sc, '_bulk_removing', 0) > 0
                or getattr(sc, '_bulk_adding', 0) > 0
            ):
                return
        except RuntimeError:
            return
        try:
            self._node.setBrush(QBrush(color))
        except RuntimeError:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # PERSONALITY — hover pulse + background glow
    # ─────────────────────────────────────────────────────────────────────────

    def on_hover_enter(self):
        """Breathe in — scale swells, background warms toward the accent."""
        # Aerial view: don't start the pulse.  The scale delta at that
        # zoom is sub-pixel and invisible; _animate_bg_to below still
        # updates the target colour but without the 60Hz tick cost.
        if self._should_pulse():
            if self.pulse_anim.state() == QVariantAnimation.Stopped:
                # Re-target the end-value each breath so live resizes
                # (and huuuge nodes) pick up the size-dampened scale
                # without separate bookkeeping. Default-sized nodes get
                # PULSE_SCALE verbatim — no behavioural drift.
                self.pulse_anim.setEndValue(self._compute_effective_pulse_scale())
                self.pulse_anim.setDirection(QVariantAnimation.Forward)
                self.pulse_anim.start()
        self._animate_bg_to(self._bg_hover(), 320)

    def on_hover_leave(self):
        """
        Breathe out — scale settles via _on_pulse_finished.
        Background returns to selected tint if selected, otherwise to normal.
        """
        if self._node is None:
            return
        target = self._bg_selected() if self._node.isSelected() else self._bg_normal()
        self._animate_bg_to(target, 450)

    def on_selected(self, is_selected: bool) -> None:
        """Background shifts to the selected tint (or back to normal on deselect)."""
        target = self._bg_selected() if is_selected else self._bg_normal()
        self._animate_bg_to(target, 180)

    def _on_pulse_value(self, value: float) -> None:
        """Apply the pulse's interpolated scale to the node, unless the scene
        is mid bulk-remove or bulk-add — in either case skip the paint-
        invalidating mutation. See _on_bg_changed for the full rationale."""
        if self._node is None:
            return
        try:
            sc = self._node.scene()
            if sc is not None and (
                getattr(sc, '_bulk_removing', 0) > 0
                or getattr(sc, '_bulk_adding', 0) > 0
            ):
                return
            self._node.setScale(value)
        except RuntimeError:
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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.pulse_anim.valueChanged.disconnect(self._on_pulse_value)
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
        self._node = None
