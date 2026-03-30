#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Connection.py Connection class
-Visual bezier wires between node ports with glow rendering for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor, QPainter, QLinearGradient, QBrush
from PySide6.QtCore import Qt, QPointF, QTimer


class Connection(QGraphicsPathItem):

    # Fraction of the remaining gap closed per ~16 ms frame (~60 fps).
    # 0.15 gives a smooth ~0.4 s ease-out glide between corners.
    _GLIDE_SPEED = 0.15

    # Pixels to inset the wire endpoint into the node from the port position
    _INSET = 8.0

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

        # z=0 — neutral between back nodes (z=-10) and front nodes (z=10).
        self.setZValue(0)
        self.update_path()

    # ------------------------------------------------------------------
    # Corner tangent helpers
    # ------------------------------------------------------------------

    def _corner_tangent(self, node, port):
        """
        Given a port on node, return (inset_scene_pos, outward_dx, outward_dy).
        The inset pos moves _INSET pixels from the corner toward the node centre.
        The outward direction is what both ctrl1 (departure) and ctrl2 (arrival)
        use — placing the control handle outside the corner so the bezier arc
        comes in/out at the correct diagonal angle.
        """
        port_local = port.pos()
        r  = node.rect()
        cx = r.width()  / 2 - port_local.x()   # vector: port → centre
        cy = r.height() / 2 - port_local.y()
        length = (cx * cx + cy * cy) ** 0.5
        if length > 0:
            nx, ny = cx / length, cy / length
        else:
            nx, ny = 1.0, 0.0
        pos = node.mapToScene(port_local + QPointF(nx * self._INSET, ny * self._INSET))
        return pos, -nx, -ny   # outward = opposite of inward

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

            self._build_bezier(
                self._anim_p1, self._anim_d1x, self._anim_d1y,
                self.floating_point, -1.0, 0.0,
            )
            return
        else:
            return

        self._build_bezier(
            self._anim_p1, self._anim_d1x, self._anim_d1y,
            self._anim_p2, self._anim_d2x, self._anim_d2y,
        )

    def _glide_tick(self):
        """Advance both animated endpoints toward their targets."""
        if self.start_node is None:
            self._glide_timer.stop()
            return

        s = self._GLIDE_SPEED

        def _lerp(a, b):
            return a + (b - a) * s

        # Departure (source end)
        ax1 = _lerp(self._anim_p1.x(), self._tgt_p1.x())
        ay1 = _lerp(self._anim_p1.y(), self._tgt_p1.y())
        dx1 = _lerp(self._anim_d1x,    self._tgt_d1x)
        dy1 = _lerp(self._anim_d1y,    self._tgt_d1y)

        # Arrival (target end)
        if self._anim_p2 is not None and self._tgt_p2 is not None:
            ax2 = _lerp(self._anim_p2.x(), self._tgt_p2.x())
            ay2 = _lerp(self._anim_p2.y(), self._tgt_p2.y())
            dx2 = _lerp(self._anim_d2x,    self._tgt_d2x)
            dy2 = _lerp(self._anim_d2y,    self._tgt_d2y)
        else:
            ax2, ay2, dx2, dy2 = None, None, self._anim_d2x, self._anim_d2y

        # Settle check — stop the timer when both ends are close enough
        p1_settled = (self._tgt_p1.x() - ax1) ** 2 + (self._tgt_p1.y() - ay1) ** 2 < 0.25
        d1_settled = (self._tgt_d1x - dx1) ** 2    + (self._tgt_d1y - dy1) ** 2    < 0.0001
        if ax2 is not None and self._tgt_p2 is not None:
            p2_settled = (self._tgt_p2.x() - ax2) ** 2 + (self._tgt_p2.y() - ay2) ** 2 < 0.25
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

    _TAPER_SEGMENTS = 96
    _FADE_OUTSIDE   = 10.0
    _FADE_INSIDE    = 22.0

    def _segment_opacity(self, pt, covering_nodes):
        if not covering_nodes:
            return 1.0
        min_opacity = 1.0
        for node in covering_nodes:
            r     = node.mapRectToScene(node.boundingRect())
            ix    = min(pt.x() - r.left(), r.right()  - pt.x())
            iy    = min(pt.y() - r.top(),  r.bottom() - pt.y())
            inset = min(ix, iy)
            span  = self._FADE_OUTSIDE + self._FADE_INSIDE
            fade  = max(0.0, min(1.0, (inset + self._FADE_OUTSIDE) / span))
            min_opacity = min(min_opacity, 1.0 - fade * 0.92)
        return min_opacity

    def paint(self, painter, option, widget):
        if self.start_node is None or not self.path():
            return

        painter.setRenderHint(QPainter.Antialiasing)

        covering_nodes = []
        scene = self.scene()
        if scene:
            for item in scene.items(self.boundingRect()):
                if hasattr(item, 'data') and item is not self.start_node \
                        and item is not self.end_node:
                    covering_nodes.append(item)

        def _wire_color(node):
            c = node.brush().color()
            h = c.hsvHueF()
            s = c.hsvSaturationF()
            v = c.valueF()
            if h < 0:
                from graphics.Theme import Theme as _T
                ref = QColor(_T.primaryBorder)
                h, s = ref.hsvHueF(), ref.hsvSaturationF() * 0.6
            return QColor.fromHsvF(
                max(0.0, h),
                min(1.0, s + 0.2),
                min(1.0, max(0.65, v * 3.0)),
            )

        c_start = _wire_color(self.start_node)
        c_end   = QColor(Theme.primaryBorder) if self.end_node else c_start

        N = self._TAPER_SEGMENTS
        for i in range(N):
            t0  = i / N
            t1  = (i + 1) / N
            t   = (t0 + t1) / 2
            pt0 = self.path().pointAtPercent(t0)
            pt1 = self.path().pointAtPercent(t1)
            pt  = self.path().pointAtPercent(t)

            seg = QPainterPath()
            seg.moveTo(pt0)
            seg.lineTo(pt1)

            seg_opacity = self._segment_opacity(pt, covering_nodes)
            glow_color  = QColor(
                int(c_start.red()   + (c_end.red()   - c_start.red())   * t),
                int(c_start.green() + (c_end.green() - c_start.green()) * t),
                int(c_start.blue()  + (c_end.blue()  - c_start.blue())  * t),
                int(255 * seg_opacity),
            )
            glow_pen = QPen(glow_color, 1.0 + t * 5.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(seg)

        p_start   = self.path().pointAtPercent(0)
        p_end     = self.path().pointAtPercent(1)
        core_grad = QLinearGradient(p_start, p_end)
        core_grad.setColorAt(0, QColor(255, 255, 255, 80))
        core_grad.setColorAt(1, QColor(255, 255, 255, 160))
        core_pen  = QPen(QBrush(core_grad), 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(core_pen)
        painter.drawPath(self.path())


# Deferred — avoids circular import since Connection lives in graphics/
from graphics.Theme import Theme
