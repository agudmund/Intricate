#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/Connection.py Connection class
-Visual bezier wires between node ports with glow rendering for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor, QLinearGradient, QPainter, QBrush
from PySide6.QtCore import Qt, QPointF


class Connection(QGraphicsPathItem):
    def __init__(self, start_node, end_node=None):
        super().__init__()

        self.floating_point = None
        self.start_node = start_node
        self.start_node.connections.append(self)
        self.end_node = end_node
        if self.end_node:
            self.end_node.connections.append(self)

        # Cache last positions to detect meaningful changes
        self._last_p1 = None
        self._last_p2 = None

        self.setZValue(-1)
        self.update_path()

    def update_path(self, mouse_pos=None):
        """Update bezier path only if endpoints have moved significantly."""
        if self.start_node is None:
            return
        self.floating_point = mouse_pos

        # Start/end points offset inward so wires visually sink into the node
        # edge rather than floating at the port centre when ports are hidden.
        _INSET = 8.0
        p1 = self.start_node.mapToScene(
            self.start_node.output_port.pos() + QPointF(-_INSET, 0)
        )

        if self.end_node:
            p2 = self.end_node.mapToScene(
                self.end_node.input_port.pos() + QPointF(_INSET, 0)
            )
        elif self.floating_point:
            p2 = self.floating_point
        else:
            return

        # Skip recalculation for sub-pixel movements
        if self._last_p1 and self._last_p2:
            dist1 = (p1.x() - self._last_p1.x()) ** 2 + (p1.y() - self._last_p1.y()) ** 2
            dist2 = (p2.x() - self._last_p2.x()) ** 2 + (p2.y() - self._last_p2.y()) ** 2
            if dist1 < 2 and dist2 < 2:
                return

        self._last_p1 = p1
        self._last_p2 = p2

        path = QPainterPath()
        path.moveTo(p1)

        horizontal_dist = p2.x() - p1.x()

        # Blend zone — interpolate between forward and backward control points
        blend_zone = 100.0
        t = max(0.0, min(1.0, (blend_zone - horizontal_dist) / (blend_zone * 2)))

        dx_fwd = max(horizontal_dist * 0.5, 80)
        fwd_c1 = QPointF(p1.x() + dx_fwd, p1.y())
        fwd_c2 = QPointF(p2.x() - dx_fwd, p2.y())

        clearance = min(max(abs(horizontal_dist) * 0.3, 80), 120)
        tilt = clearance * 0.5
        bwd_c1 = QPointF(p1.x() + clearance * 1.2, p1.y())
        bwd_c2 = QPointF(p2.x() + clearance * 1.2, p2.y() - tilt * 0.5)

        def lerp_pt(a, b, t):
            return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)

        ctrl1 = lerp_pt(fwd_c1, bwd_c1, t)
        ctrl2 = lerp_pt(fwd_c2, bwd_c2, t)
        path.cubicTo(ctrl1, ctrl2, p2)
        self.setPath(path)

    def paint(self, painter, option, widget):
        if self.start_node is None or not self.path():
            return

        painter.setRenderHint(QPainter.Antialiasing)

        p1 = self.path().pointAtPercent(0)
        p2 = self.path().pointAtPercent(1)

        grad = QLinearGradient(p1, p2)
        grad.setColorAt(0, QColor(Theme.wireStart))
        grad.setColorAt(1, QColor(Theme.wireEnd))

        # Glow pass — thicker, semi-transparent
        glow_pen = QPen(QBrush(grad), 6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawPath(self.path())

        # Core pass — thin, bright white centre
        core_color = QColor("#ffffff")
        core_color.setAlpha(150)
        core_pen = QPen(core_color, 1.5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(core_pen)
        painter.drawPath(self.path())


# Deferred — avoids circular import since Connection lives in graphics/
from graphics.Theme import Theme
