#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Connection.py Connection class
-Visual bezier wires between node ports with glow rendering for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainterPath, QPen, QColor, QPainter
from PySide6.QtCore import Qt, QPointF, QTimer
from shiboken6 import isValid as _shibokenIsValid

# Aerial-altitude threshold — wires drop entirely below this LOD. Kept as
# a literal here to avoid importing from `nodes/` into `graphics/`
# (Connection lives in graphics/, BaseNode in nodes/, and graphics/
# deliberately stays independent).
#
# Intentionally split from BaseNode.AERIAL_LOD_THRESHOLD (0.07) — wires
# higher, nodes lower. At 0.15 wires are already sub-pixel and produce
# no visible ribbon, so the wire-skip below 0.15 is invisible to the
# user but reclaims a meaningful slice of paint cost (Bezier evaluation
# across many wires per zoom frame) for the whole 0.07–0.15 band where
# nodes are still painting their natural pipeline. The visible aerial
# transition is gated by the BaseNode threshold; the wire threshold is
# a pure perf gate.
_AERIAL_LOD_THRESHOLD = 0.15

from utils.motion.MotionCurves import GlideEngine


def _endpoint_alive(node) -> bool:
    """An endpoint is safe to paint/glide against only while its C++ side
    is still valid AND it is still attached to a scene. After removeItem()
    or deleteLater() the Python ref can linger while the widget pointer
    is already freed — dereferencing it segfaults Qt6Widgets.dll."""
    if node is None:
        return False
    try:
        if not _shibokenIsValid(node):
            return False
        return node.scene() is not None
    except RuntimeError:
        return False


class Connection(QGraphicsPathItem):

    # Pixels past the node border the wire endpoint is placed.
    # Previously 18px inside the node with a paint-time clip fade — now that
    # wires render above nodes the endpoint sits right at the border.
    _INSIDE = 0.0

    def __init__(self, start_node, end_node=None):
        super().__init__()

        self.floating_point  = None
        self.start_node      = start_node
        self.start_node.connections.append(self)
        self.end_node        = end_node
        self.end_input_port  = None   # legacy slot — routing is now dynamic
        if self.end_node:
            self.end_node.connections.append(self)

        # Motion engine — owns all animated/target state and the glide math
        self._engine = GlideEngine()

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

        # Borderless nodes (e.g. ValueNode) skip the _INSIDE projection entirely —
        # the wire terminates exactly at the port's position.
        if getattr(node, '_wire_at_port', False):
            return node.mapToScene(port.pos()), odx, ody

        # Inward direction drives the parametric border-crossing calculation.
        nx, ny = -odx, -ody

        t_x = ((r.left()   - px) / nx) if nx > 1e-6  else \
              ((r.right()  - px) / nx) if nx < -1e-6 else 0.0
        t_y = ((r.top()    - py) / ny) if ny > 1e-6  else \
              ((r.bottom() - py) / ny) if ny < -1e-6 else 0.0
        t_border = max(t_x, t_y)

        # Corner ports land on the square rect edge, but the visible border
        # is beveled inward by round_radius.  Push the endpoint outward along
        # the diagonal by the gap between the square corner and the arc.
        bevel_offset = 0.0
        if ax > 0.5 and ay > 0.5:
            rr = node.round_radius if hasattr(node, 'round_radius') else 0.0
            bevel_offset = rr * (1.0 - 0.7071)  # 1 - 1/√2

        pos = node.mapToScene(QPointF(
            px + nx * (t_border + self._INSIDE) - odx * bevel_offset,
            py + ny * (t_border + self._INSIDE) - ody * bevel_offset,
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
        """Place the wire above all nodes so it is always visible."""
        self.setZValue(9999.0)

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
        e = self._engine

        if self.end_node:
            # Use node centres as stable references for corner selection —
            # avoids any circular dependency between the two ends.
            src_centre = self._node_center(self.start_node)
            end_centre = self._node_center(self.end_node)

            tgt_p1, tgt_d1x, tgt_d1y = self._compute_source(end_centre)
            tgt_p2, tgt_d2x, tgt_d2y = self._compute_target(src_centre)

            e.set_source_target(tgt_p1, tgt_d1x, tgt_d1y)
            e.set_target_target(tgt_p2, tgt_d2x, tgt_d2y)

            if e.anim_p1 is None:
                # First draw — snap both ends directly, no glide
                e.snap_source(tgt_p1, tgt_d1x, tgt_d1y)
                e.snap_target(tgt_p2, tgt_d2x, tgt_d2y)
            elif e.anim_p2 is None:
                # Completing a previously floating wire — source end was tracking the
                # mouse so anim_p1 is set, but the target end was never initialised.
                # Snap it now so _build_bezier always receives two valid QPointFs.
                e.snap_target(tgt_p2, tgt_d2x, tgt_d2y)
                if not self._glide_timer.isActive():
                    self._glide_timer.start()
            elif not self._glide_timer.isActive():
                self._glide_timer.start()

        elif self.floating_point:
            # Floating wire: source corner tracks the mouse, target is the cursor
            tgt_p1, tgt_d1x, tgt_d1y = self._compute_source(self.floating_point)
            e.set_source_target(tgt_p1, tgt_d1x, tgt_d1y)

            if e.anim_p1 is None:
                e.snap_source(tgt_p1, tgt_d1x, tgt_d1y)

            if not self._glide_timer.isActive():
                self._glide_timer.start()

            self._sync_z()
            self._build_bezier(
                e.anim_p1, e.anim_d1x, e.anim_d1y,
                self.floating_point, -1.0, 0.0,
            )
            return
        else:
            return

        self._sync_z()
        self._build_bezier(
            e.anim_p1, e.anim_d1x, e.anim_d1y,
            e.anim_p2, e.anim_d2x, e.anim_d2y,
        )

    def _glide_tick(self):
        """Advance the motion engine one frame and rebuild the bezier."""
        if self.start_node is None:
            self._glide_timer.stop()
            return
        # Peer-paint-during-burst guard: if the scene is mid bulk removal
        # OR bulk addition, park this tick. update() here would invalidate
        # a region whose widget may already be freed (remove case) or
        # cascade paint invalidation across the import's other wires (add
        # case — see Scene.import_session for the 89-node hang rationale).
        sc = self.scene()
        if sc is not None and (
            getattr(sc, '_bulk_removing', 0) > 0
            or getattr(sc, '_bulk_adding', 0) > 0
        ):
            return
        if not _endpoint_alive(self.start_node):
            self._glide_timer.stop()
            self.start_node = None
            return
        if self.end_node is not None and not _endpoint_alive(self.end_node):
            self._glide_timer.stop()
            self.end_node = None
            return

        e = self._engine
        settled = e.tick()

        if settled:
            self._glide_timer.stop()

        self._sync_z()
        if e.anim_p2 is not None:
            self._build_bezier(
                e.anim_p1, e.anim_d1x, e.anim_d1y,
                e.anim_p2, e.anim_d2x, e.anim_d2y,
            )
        elif self.floating_point:
            self._build_bezier(
                e.anim_p1, e.anim_d1x, e.anim_d1y,
                self.floating_point, -1.0, 0.0,
            )
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget):
        if self.start_node is None or not self.path():
            return
        # Endpoint validity: a peer may have been torn down earlier this tick
        # while this wire is still scheduled to paint. Dereferencing a freed
        # C++ QGraphicsItem from the paint loop is the 0xc0000005 crash path.
        if not _endpoint_alive(self.start_node):
            return
        if self.end_node is not None and not _endpoint_alive(self.end_node):
            return

        # Aerial-altitude bypass: at navigation zoom, the canvas reads as a
        # map of node positions; per-frame Bezier evaluation across many
        # wires is the second-largest paint cost behind word-wrapped text
        # rendering. Skip entirely — topology is conveyed by node positions.
        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
        if lod < _AERIAL_LOD_THRESHOLD:
            return

        painter.setRenderHint(QPainter.Antialiasing)

        # Wires render above all nodes — no clip cutout needed.
        path = self.path()

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
            painter.drawPath(path)
        else:
            # QPen gradient-brush strokes are unreliable in Qt — segment the bezier instead.
            # SquareCap extends each segment by half line-width at both ends, sealing joints
            # so there are no gaps or bumps between segments.  64 steps keeps per-step color
            # delta below ~2 RGB units in the transition zone — visually continuous.
            SEGMENTS  = 64
            FADE      = 0.30   # fraction of path at each end that carries the glow
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

        # ── Anchor dots at each endpoint ─────────────────────────────────
        dot_r = Theme.nodeBorderWidth * 3.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(c_start)
        p0 = path.pointAtPercent(0.0)
        painter.drawEllipse(p0, dot_r, dot_r)
        p1 = path.pointAtPercent(1.0)
        painter.setBrush(c_end)
        painter.drawEllipse(p1, dot_r, dot_r)


# Deferred — avoids circular import since Connection lives in graphics/
from pretty_widgets.graphics.Theme import Theme
