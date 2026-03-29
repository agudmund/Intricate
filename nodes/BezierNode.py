#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/BezierNode.py BezierNode class
-A smooth cubic bezier curve node with draggable control handles for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsObject, QGraphicsEllipseItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QBrush

from .BaseNode import BaseNode
from data.BezierNodeData import BezierNodeData
from graphics.Theme import Theme


# Visual constants resolved from Theme at import time
_CURVE_WIDTH     = Theme.bezierCurveWidth
_CURVE_COLOR     = Theme.bezierCurveColor
_CURVE_COLOR_SEL = Theme.bezierCurveColorSel
_HANDLE_RADIUS   = Theme.bezierHandleRadius
_HANDLE_COLOR    = Theme.bezierHandleColor
_HANDLE_HOVER    = Theme.bezierHandleHover
_ARM_COLOR       = Theme.bezierArmColor
_ARM_WIDTH       = Theme.bezierArmWidth


class _BezierHandle(QGraphicsEllipseItem):
    """
    A draggable control point handle.

    Lives as a child of the BezierNode. Dragging it updates the
    corresponding cp1/cp2 offset in BezierNodeData and triggers
    a repaint of the parent node's curve.

    Constrained to stay within the node's bounding rect so handles
    never wander off into empty space.
    """

    def __init__(self, parent: 'BezierNode', is_cp1: bool):
        r = _HANDLE_RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)

        self._node  = parent
        self._is_cp1 = is_cp1
        self._dragging = False

        self.setBrush(QBrush(QColor(_HANDLE_COLOR)))
        self.setPen(QPen(QColor(_HANDLE_COLOR).lighter(140), 1.0))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(10)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(QBrush(QColor(_HANDLE_HOVER)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setBrush(QBrush(QColor(_HANDLE_COLOR)))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.scenePos()
            self._handle_start = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return

        # Compute new position in node-local coordinates
        scene_delta  = event.scenePos() - self._drag_start
        new_pos      = self._handle_start + QPointF(
            scene_delta.x() / self._node.transform().m11() if self._node.transform().m11() != 0 else scene_delta.x(),
            scene_delta.y() / self._node.transform().m22() if self._node.transform().m22() != 0 else scene_delta.y(),
        )

        # Clamp to node rect with handle radius margin
        r   = self._node.rect()
        margin = _HANDLE_RADIUS
        new_pos = QPointF(
            max(r.left()  + margin, min(r.right()  - margin, new_pos.x())),
            max(r.top()   + margin, min(r.bottom() - margin, new_pos.y())),
        )

        self.setPos(new_pos)

        # Write back to data
        if self._is_cp1:
            self._node.data.cp1_x = new_pos.x()
            self._node.data.cp1_y = new_pos.y()
        else:
            self._node.data.cp2_x = new_pos.x()
            self._node.data.cp2_y = new_pos.y()

        self._node.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class BezierNode(BaseNode):
    """
    A cubic bezier curve node with two draggable control handles.

    The curve runs from the left-center to the right-center of the node body.
    Two handles (cp1, cp2) control the curve's shape — drag them to reshape.
    Thin arms connect each endpoint to its handle for visual clarity.

    Data flow role:
        Passthrough — emits whatever arrives at its input port unchanged.
        The curve is a visual waypoint, not a transformation.
        The bezier shape itself is purely aesthetic.

    Serialization:
        Control handle positions are stored as node-local coordinates
        in BezierNodeData. The curve is always fully reconstructible
        from those two points plus the node geometry.
    """

    def __init__(self, data: BezierNodeData | None = None):
        if data is None:
            data = BezierNodeData()
        super().__init__(data)

        # Override the default node background to be mostly transparent —
        # the bezier node is about the curve, not the box
        self.setBrush(QColor(Theme.nodeBg).darker(110))

        # Build the two draggable handles
        self._handle1: _BezierHandle | None = None
        self._handle2: _BezierHandle | None = None
        self._build_handles()

    # ─────────────────────────────────────────────────────────────────────────
    # HANDLES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_handles(self) -> None:
        """
        Create the two control handles and position them.

        On first creation (no saved positions) the handles are placed at
        a gentle default spread — one third and two thirds across the node,
        offset vertically to create an immediate S-curve.

        On restore from session the saved positions are used directly.
        """
        data = self.data
        r    = self.rect()

        if not data._handles_initialised:
            # Default positions — pleasant S-curve spread
            data.cp1_x = r.left()  + r.width()  * 0.33
            data.cp1_y = r.top()   + r.height()  * 0.25
            data.cp2_x = r.left()  + r.width()  * 0.67
            data.cp2_y = r.top()   + r.height()  * 0.75
            data._handles_initialised = True

        self._handle1 = _BezierHandle(self, is_cp1=True)
        self._handle1.setPos(QPointF(data.cp1_x, data.cp1_y))

        self._handle2 = _BezierHandle(self, is_cp1=False)
        self._handle2.setPos(QPointF(data.cp2_x, data.cp2_y))

    def _curve_endpoints(self) -> tuple[QPointF, QPointF]:
        """
        Derive the curve start and end from the current node rect.
        Always left-center → right-center.
        """
        r  = self.rect()
        cy = r.top() + r.height() / 2.0
        return QPointF(r.left(), cy), QPointF(r.right(), cy)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        p0, p3  = self._curve_endpoints()
        cp1 = QPointF(self.data.cp1_x, self.data.cp1_y)
        cp2 = QPointF(self.data.cp2_x, self.data.cp2_y)

        # ── Control arms — thin lines from endpoints to handles ───────────────
        arm_pen = QPen(QColor(_ARM_COLOR), _ARM_WIDTH, Qt.DashLine)
        arm_pen.setDashPattern([4.0, 4.0])
        painter.setPen(arm_pen)
        painter.drawLine(p0, cp1)
        painter.drawLine(p3, cp2)

        # ── Bezier curve ───────────────────────────────────────────────────────
        path = QPainterPath()
        path.moveTo(p0)
        path.cubicTo(cp1, cp2, p3)

        curve_color = _CURVE_COLOR_SEL if self.isSelected() else _CURVE_COLOR
        curve_pen   = QPen(QColor(curve_color), _CURVE_WIDTH, Qt.SolidLine)
        curve_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(curve_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        """On resize, clamp handles to stay within the new bounds."""
        super().setRect(rect)
        if self._handle1 and self._handle2:
            margin = _HANDLE_RADIUS
            for handle in (self._handle1, self._handle2):
                p = handle.pos()
                clamped = QPointF(
                    max(rect.left()  + margin, min(rect.right()  - margin, p.x())),
                    max(rect.top()   + margin, min(rect.bottom() - margin, p.y())),
                )
                handle.setPos(clamped)
            # Sync clamped positions back to data
            self.data.cp1_x = self._handle1.pos().x()
            self.data.cp1_y = self._handle1.pos().y()
            self.data.cp2_x = self._handle2.pos().x()
            self.data.cp2_y = self._handle2.pos().y()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._handle1 = None
        self._handle2 = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        """Sync handle positions back to data before serialization."""
        super().sync_data()
        if self._handle1:
            self.data.cp1_x = self._handle1.pos().x()
            self.data.cp1_y = self._handle1.pos().y()
        if self._handle2:
            self.data.cp2_x = self._handle2.pos().x()
            self.data.cp2_y = self._handle2.pos().y()

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'BezierNode':
        return BezierNode(BezierNodeData.from_dict(data))
