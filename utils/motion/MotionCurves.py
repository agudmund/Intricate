#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/MotionCurves.py wire motion engine
-Decoupled glide animation for bezier wire endpoints for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import QPointF


def lerp(a: float, b: float, speed: float) -> float:
    """Linear interpolation by a fraction of the remaining gap."""
    return a + (b - a) * speed


class GlideEngine:
    """
    Drives the smooth ease-out glide of bezier wire endpoints.

    Owns all animated and target state for both ends of a wire.
    Each tick lerps animated values toward their targets at two speeds:
    a slower one for endpoint positions (large distances) and a faster
    one for tangent directions (curve flex).

    The engine is pure math — no Qt rendering, no scene awareness.
    Connection creates one instance and calls tick() from its QTimer.

    Tuning constants:
        glide_speed      — tangent lerp fraction per frame (curve flex)
        port_glide_speed — position lerp fraction per frame (endpoint slide)
        settle_pos       — squared-distance threshold for position convergence
        settle_dir       — squared-distance threshold for tangent convergence
    """

    def __init__(
        self,
        glide_speed:      float = 0.07,
        port_glide_speed: float = 0.04,
        settle_pos:       float = 0.04,
        settle_dir:       float = 0.0001,
    ):
        self.glide_speed      = glide_speed
        self.port_glide_speed = port_glide_speed
        self.settle_pos       = settle_pos
        self.settle_dir       = settle_dir

        # Animated state (current visual position)
        self.anim_p1:  QPointF | None = None
        self.anim_d1x: float =  1.0
        self.anim_d1y: float =  0.0

        self.anim_p2:  QPointF | None = None
        self.anim_d2x: float = -1.0
        self.anim_d2y: float =  0.0

        # Target state (where the endpoints are heading)
        self.tgt_p1:  QPointF | None = None
        self.tgt_d1x: float =  1.0
        self.tgt_d1y: float =  0.0

        self.tgt_p2:  QPointF | None = None
        self.tgt_d2x: float = -1.0
        self.tgt_d2y: float =  0.0

    def snap_source(self, p: QPointF, dx: float, dy: float) -> None:
        """Instantly set both animated and target state for the source end."""
        self.anim_p1, self.anim_d1x, self.anim_d1y = p, dx, dy
        self.tgt_p1,  self.tgt_d1x,  self.tgt_d1y  = p, dx, dy

    def snap_target(self, p: QPointF, dx: float, dy: float) -> None:
        """Instantly set both animated and target state for the target end."""
        self.anim_p2, self.anim_d2x, self.anim_d2y = p, dx, dy
        self.tgt_p2,  self.tgt_d2x,  self.tgt_d2y  = p, dx, dy

    def set_source_target(self, p: QPointF, dx: float, dy: float) -> None:
        """Update where the source end should glide toward."""
        self.tgt_p1, self.tgt_d1x, self.tgt_d1y = p, dx, dy

    def set_target_target(self, p: QPointF, dx: float, dy: float) -> None:
        """Update where the arrival end should glide toward."""
        self.tgt_p2, self.tgt_d2x, self.tgt_d2y = p, dx, dy

    def tick(self) -> bool:
        """Advance one frame of the glide animation.

        Returns True if the animation has settled (both ends converged),
        False if more frames are needed.
        """
        sp = self.port_glide_speed
        st = self.glide_speed

        # Source end
        ax1 = lerp(self.anim_p1.x(), self.tgt_p1.x(), sp)
        ay1 = lerp(self.anim_p1.y(), self.tgt_p1.y(), sp)
        dx1 = lerp(self.anim_d1x,    self.tgt_d1x,    st)
        dy1 = lerp(self.anim_d1y,    self.tgt_d1y,    st)

        # Target end
        if self.anim_p2 is not None and self.tgt_p2 is not None:
            ax2 = lerp(self.anim_p2.x(), self.tgt_p2.x(), sp)
            ay2 = lerp(self.anim_p2.y(), self.tgt_p2.y(), sp)
            dx2 = lerp(self.anim_d2x,    self.tgt_d2x,    st)
            dy2 = lerp(self.anim_d2y,    self.tgt_d2y,    st)
        else:
            ax2, ay2, dx2, dy2 = None, None, self.anim_d2x, self.anim_d2y

        # Settle check
        p1_ok = (self.tgt_p1.x() - ax1) ** 2 + (self.tgt_p1.y() - ay1) ** 2 < self.settle_pos
        d1_ok = (self.tgt_d1x - dx1) ** 2    + (self.tgt_d1y - dy1) ** 2    < self.settle_dir
        if ax2 is not None and self.tgt_p2 is not None:
            p2_ok = (self.tgt_p2.x() - ax2) ** 2 + (self.tgt_p2.y() - ay2) ** 2 < self.settle_pos
            d2_ok = (self.tgt_d2x - dx2) ** 2    + (self.tgt_d2y - dy2) ** 2    < self.settle_dir
        else:
            p2_ok = d2_ok = True

        settled = p1_ok and d1_ok and p2_ok and d2_ok

        if settled:
            self.anim_p1, self.anim_d1x, self.anim_d1y = self.tgt_p1, self.tgt_d1x, self.tgt_d1y
            if self.tgt_p2 is not None:
                self.anim_p2, self.anim_d2x, self.anim_d2y = self.tgt_p2, self.tgt_d2x, self.tgt_d2y
        else:
            self.anim_p1  = QPointF(ax1, ay1)
            self.anim_d1x = dx1
            self.anim_d1y = dy1
            if ax2 is not None:
                self.anim_p2  = QPointF(ax2, ay2)
                self.anim_d2x = dx2
                self.anim_d2y = dy2

        return settled
