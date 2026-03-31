#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Connection.py Connection class
-Visual bezier wires between node ports with glow rendering for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor, QPainter
from PySide6.QtCore import Qt, QPointF, QTimer


class Connection(QGraphicsPathItem):

    # Fraction of the remaining tangent gap closed per frame (controls curve shape flex).
    # 0.07 gives a gentle ~0.8 s ease-out; feels rubbery without being sluggish.
    _GLIDE_SPEED = 0.07

    # Separate, slower lerp for endpoint positions — port-to-port slides cover
    # more distance than tangent rotations so they need a lower fraction to feel
    # as unhurried as the curve deformation.
    _PORT_GLIDE_SPEED = 0.04

    # Pixels past the node border the wire endpoint is placed.
    # The wire is then faded out over this same distance so it is only
    # visible up to the edge — extending inside avoids a visible gap.
    _INSIDE = 18.0

    def __init__(self, start_node, end_node=None):
        super().__init__()

        self.floating_point  = None
        self.start_node      = start_node
        self.start_node.connections.append(self)
        self.end_node        = end_node
        self.end_input_port  = None   # legacy slot — routing is now dynamic
        if self.end_node:
            self.end_node.connections.append(self)

        # Animated departure state (source end)
        self._anim_p1  = None
        self._anim_d1x =  1.0
        self._anim_d1y =  0.0

        # Target departure state
        self._tgt_p1   = None
        self._tgt_d1x  =  1.0
        self._tgt_d1y  =  0.0

        # Animated arrival state (target end)
        self._anim_p2  = None
        self._anim_d2x = -1.0
        self._anim_d2y =  0.0

        # Target arrival state
        self._tgt_p2   = None
        self._tgt_d2x  = -1.0
        self._tgt_d2y  =  0.0

        # Timer drives the glide animation independently of node-move events
        self._glide_timer = QTimer()
        self._glide_timer.setInterval(16)
        self._glide_timer.timeout.connect(self._glide_tick)

        self.update_path()   # also sets z via _sync_z()

    # ------------------------------------------------------------------
    # Corner tangent helpers
    # ------------------------------------------------------------------

    def _corner_tangent(self, node, port):
        """
        Given a port on node, return (endpoint_scene_pos, outward_dx, outward_dy).

        The endpoint is placed _INSIDE pixels past the node border so the
        bezier terminates well inside the node.  The wire is then faded out
        over that same distance in paint() so it is only visible up to the edge.

        Outward direction is determined by port classification, not raw geometry,
        so the tangent is always consistent with the node border:
          - Mid-edge ports  →  pure perpendicular to that edge (0,±1 or ±1,0)
          - Corner ports    →  true 45° diagonal regardless of node aspect ratio
        This matches the curvature flow of the rounded-rect border at every port.
        """
        port_local = port.pos()
        r  = node.rect()
        px, py = port_local.x(), port_local.y()
        half_w = r.width()  / 2 if r.width()  > 1e-6 else 1.0
        half_h = r.height() / 2 if r.height() > 1e-6 else 1.0

        # Normalised position relative to node centre.
        # |rel| > 1 means the port is outside the rect on that axis.
        rel_x = (px - half_w) / half_w
        rel_y = (py - half_h) / half_h
        ax, ay = abs(rel_x), abs(rel_y)

        # Classify: corner port if both axes are at the boundary (> 0.5),
        # mid-edge port if only one axis is at the boundary.
        if ax > 0.5 and ay > 0.5:
            # Corner — use a true 45° diagonal so the wire honours the bevel arc
            # regardless of node width/height ratio.
            odx = 1.0 if rel_x > 0 else -1.0
            ody = 1.0 if rel_y > 0 else -1.0
            inv = (odx * odx + ody * ody) ** -0.5
            odx *= inv
            ody *= inv
        elif ax >= ay:
            # Mid-edge on left or right face
            odx = 1.0 if rel_x > 0 else -1.0
            ody = 0.0
        else:
            # Mid-edge on top or bottom face
            odx = 0.0
            ody = 1.0 if rel_y > 0 else -1.0

        # Inward direction drives the parametric border-crossing calculation.
        nx, ny = -odx, -ody

        t_x = ((r.left()   - px) / nx) if nx > 1e-6  else \
              ((r.right()  - px) / nx) if nx < -1e-6 else 0.0
        t_y = ((r.top()    - py) / ny) if ny > 1e-6  else \
              ((r.bottom() - py) / ny) if ny < -1e-6 else 0.0
        t_border = max(t_x, t_y)

        pos = node.mapToScene(QPointF(
            px + nx * (t_border + self._INSIDE),
            py + ny * (t_border + self._INSIDE),
        ))
        return pos, odx, ody

    def _compute_source(self, ref_scene_pos):
        """Pick the output corner of start_node closest to ref_scene_pos."""
        port = self.start_node.closest_output_port(ref_scene_pos)
        return self._corner_tangent(self.start_node, port)

    def _compute_target(self, ref_scene_pos):
        """Pick the input corner of end_node closest to ref_scene_pos."""
        port = self.end_node.closest_input_port(ref_scene_pos)
        return self._corner_tangent(self.end_node, port)

    @staticmethod
    def _node_center(node):
        return node.mapToScene(node.rect().center())

    def _sync_z(self):
        """
        Match the wire's z to its lowest endpoint node.  Same-z ties are broken
        by scene insertion order — nodes are added before wires, so nodes still
        paint over the wire without the sub-pixel render-order seam that
        z - epsilon introduced at the thin source end of the taper.
        """
        z = self.start_node.zValue()
        if self.end_node:
            z = min(z, self.end_node.zValue())
        self.setZValue(z)

    # ------------------------------------------------------------------
    # Path construction
    # ------------------------------------------------------------------

    def _build_bezier(self, p1, d1x, d1y, p2, d2x, d2y):
        """Construct and set the cubic bezier path from the given values."""
        chord  = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
        handle = max(80.0, chord * 0.45)
        ctrl1  = QPointF(p1.x() + d1x * handle, p1.y() + d1y * handle)
        ctrl2  = QPointF(p2.x() + d2x * handle, p2.y() + d2y * handle)
        path   = QPainterPath()
        path.moveTo(p1)
        path.cubicTo(ctrl1, ctrl2, p2)
        self.setPath(path)

    def update_path(self, mouse_pos=None):
        """Called whenever a connected node moves. Refreshes targets and path."""
        if self.start_node is None:
            return
        self.floating_point = mouse_pos

        if self.end_node:
            # Use node centres as stable references for corner selection —
            # avoids any circular dependency between the two ends.
            src_centre = self._node_center(self.start_node)
            end_centre = self._node_center(self.end_node)

            tgt_p1, tgt_d1x, tgt_d1y = self._compute_source(end_centre)
            tgt_p2, tgt_d2x, tgt_d2y = self._compute_target(src_centre)

            self._tgt_p1, self._tgt_d1x, self._tgt_d1y = tgt_p1, tgt_d1x, tgt_d1y
            self._tgt_p2, self._tgt_d2x, self._tgt_d2y = tgt_p2, tgt_d2x, tgt_d2y

            if self._anim_p1 is None:
                # First draw — snap both ends directly, no glide
                self._anim_p1, self._anim_d1x, self._anim_d1y = tgt_p1, tgt_d1x, tgt_d1y
                self._anim_p2, self._anim_d2x, self._anim_d2y = tgt_p2, tgt_d2x, tgt_d2y
            elif self._anim_p2 is None:
                # Completing a previously floating wire — source end was tracking the
                # mouse so _anim_p1 is set, but the target end was never initialised.
                # Snap it now so _build_bezier always receives two valid QPointFs.
                self._anim_p2, self._anim_d2x, self._anim_d2y = tgt_p2, tgt_d2x, tgt_d2y
                if not self._glide_timer.isActive():
                    self._glide_timer.start()
            elif not self._glide_timer.isActive():
                self._glide_timer.start()

        elif self.floating_point:
            # Floating wire: source corner tracks the mouse, target is the cursor
            tgt_p1, tgt_d1x, tgt_d1y = self._compute_source(self.floating_point)
            self._tgt_p1, self._tgt_d1x, self._tgt_d1y = tgt_p1, tgt_d1x, tgt_d1y

            if self._anim_p1 is None:
                self._anim_p1, self._anim_d1x, self._anim_d1y = tgt_p1, tgt_d1x, tgt_d1y

            if not self._glide_timer.isActive():
                self._glide_timer.start()

            self._sync_z()
            self._build_bezier(
                self._anim_p1, self._anim_d1x, self._anim_d1y,
                self.floating_point, -1.0, 0.0,
            )
            return
        else:
            return

        self._sync_z()
        self._build_bezier(
            self._anim_p1, self._anim_d1x, self._anim_d1y,
            self._anim_p2, self._anim_d2x, self._anim_d2y,
        )

    def _glide_tick(self):
        """Advance both animated endpoints toward their targets."""
        if self.start_node is None:
            self._glide_timer.stop()
            return

        sp = self._PORT_GLIDE_SPEED   # slower — for endpoint positions
        st = self._GLIDE_SPEED        # faster — for tangent directions (curve flex)

        def _lerp(a, b, s):
            return a + (b - a) * s

        # Departure (source end)
        ax1 = _lerp(self._anim_p1.x(), self._tgt_p1.x(), sp)
        ay1 = _lerp(self._anim_p1.y(), self._tgt_p1.y(), sp)
        dx1 = _lerp(self._anim_d1x,    self._tgt_d1x,    st)
        dy1 = _lerp(self._anim_d1y,    self._tgt_d1y,    st)

        # Arrival (target end)
        if self._anim_p2 is not None and self._tgt_p2 is not None:
            ax2 = _lerp(self._anim_p2.x(), self._tgt_p2.x(), sp)
            ay2 = _lerp(self._anim_p2.y(), self._tgt_p2.y(), sp)
            dx2 = _lerp(self._anim_d2x,    self._tgt_d2x,    st)
            dy2 = _lerp(self._anim_d2y,    self._tgt_d2y,    st)
        else:
            ax2, ay2, dx2, dy2 = None, None, self._anim_d2x, self._anim_d2y

        # Settle check — stop the timer when both ends are close enough
        p1_settled = (self._tgt_p1.x() - ax1) ** 2 + (self._tgt_p1.y() - ay1) ** 2 < 0.04
        d1_settled = (self._tgt_d1x - dx1) ** 2    + (self._tgt_d1y - dy1) ** 2    < 0.0001
        if ax2 is not None and self._tgt_p2 is not None:
            p2_settled = (self._tgt_p2.x() - ax2) ** 2 + (self._tgt_p2.y() - ay2) ** 2 < 0.04
            d2_settled = (self._tgt_d2x - dx2) ** 2    + (self._tgt_d2y - dy2) ** 2    < 0.0001
        else:
            p2_settled = d2_settled = True

        if p1_settled and d1_settled and p2_settled and d2_settled:
            self._anim_p1, self._anim_d1x, self._anim_d1y = self._tgt_p1, self._tgt_d1x, self._tgt_d1y
            if self._tgt_p2 is not None:
                self._anim_p2, self._anim_d2x, self._anim_d2y = self._tgt_p2, self._tgt_d2x, self._tgt_d2y
            self._glide_timer.stop()
        else:
            self._anim_p1  = QPointF(ax1, ay1)
            self._anim_d1x = dx1
            self._anim_d1y = dy1
            if ax2 is not None:
                self._anim_p2  = QPointF(ax2, ay2)
                self._anim_d2x = dx2
                self._anim_d2y = dy2

        self._sync_z()
        if self._anim_p2 is not None:
            self._build_bezier(
                self._anim_p1, self._anim_d1x, self._anim_d1y,
                self._anim_p2, self._anim_d2x, self._anim_d2y,
            )
        elif self.floating_point:
            self._build_bezier(
                self._anim_p1, self._anim_d1x, self._anim_d1y,
                self.floating_point, -1.0, 0.0,
            )
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget):
        if self.start_node is None or not self.path():
            return

        painter.setRenderHint(QPainter.Antialiasing)

        # Clip out the interior of both endpoint nodes.
        clip = QPainterPath()
        clip.addRect(self.boundingRect())
        for ep in (self.start_node, self.end_node):
            if ep is None:
                continue
            try:
                rr     = ep.round_radius if hasattr(ep, 'round_radius') else 0
                bw     = ep.current_pen.widthF() if hasattr(ep, 'current_pen') else 2.0
                margin = bw / 2.0
                cutout = QPainterPath()
                cutout.addRoundedRect(
                    ep.rect().adjusted(-margin, -margin, margin, margin),
                    rr + margin, rr + margin,
                )
                clip = clip.subtracted(ep.sceneTransform().map(cutout))
            except RuntimeError:
                pass
        painter.setClipPath(clip)

        def _ep_color(node):
            if node is not None and node.isSelected():
                return QColor(Theme.nodeBorderSelected)
            return QColor(Theme.nodeBorder)

        c_start = _ep_color(self.start_node)
        c_end   = _ep_color(self.end_node)
        c_mid   = QColor(Theme.nodeBorder)

        # If no endpoint is selected both colors equal c_mid — draw solid, skip segments.
        if c_start.rgb() == c_mid.rgb() and c_end.rgb() == c_mid.rgb():
            pen = QPen(c_mid, Theme.nodeBorderWidth, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(self.path())
            return

        # QPen gradient-brush strokes are unreliable in Qt — segment the bezier instead.
        # SquareCap extends each segment by half line-width at both ends, sealing joints
        # so there are no gaps or bumps between segments.  64 steps keeps per-step color
        # delta below ~2 RGB units in the transition zone — visually continuous.
        SEGMENTS  = 64
        FADE      = 0.30   # fraction of path at each end that carries the glow
        path      = self.path()
        bw        = Theme.nodeBorderWidth

        def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
            t = max(0.0, min(1.0, t))
            return QColor(
                int(a.red()   + (b.red()   - a.red())   * t),
                int(a.green() + (b.green() - a.green()) * t),
                int(a.blue()  + (b.blue()  - a.blue())  * t),
            )

        def _color_at(t: float) -> QColor:
            if t <= FADE:
                return _lerp_color(c_start, c_mid, t / FADE)
            if t >= 1.0 - FADE:
                return _lerp_color(c_mid, c_end, (t - (1.0 - FADE)) / FADE)
            return c_mid

        prev = path.pointAtPercent(0.0)
        for i in range(1, SEGMENTS + 1):
            t    = i / SEGMENTS
            curr = path.pointAtPercent(t)
            seg  = QPainterPath()
            seg.moveTo(prev)
            seg.lineTo(curr)
            pen = QPen(_color_at(t - 0.5 / SEGMENTS), bw,
                       Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
            painter.setPen(pen)
            painter.drawPath(seg)
            prev = curr


# Deferred — avoids circular import since Connection lives in graphics/
from graphics.Theme import Theme
