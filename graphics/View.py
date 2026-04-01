#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/View.py IntricateView class
-The window into the world. Renders the scene, handles navigation and OS drops for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


class IntricateView(QGraphicsView):
    """
    The viewport into IntricateScene.

    Responsibilities:
        - Renders the scene with correct background and antialiasing
        - Handles pan (middle mouse) and zoom (wheel, cursor-anchored)
        - Receives OS drag-and-drop events and routes image files to the scene

    Navigation ledger:
        current_zoom tracks the applied scale factor — single source of truth
        for zoom limits and any external camera sync.

    Drag and drop:
        Image files dragged from Explorer land here. The view maps the drop
        position to scene coordinates and delegates to scene.add_image_node().
        Multiple files dropped together are staggered so they don't overlap.
    """

    ZOOM_MIN = 0.1
    ZOOM_MAX = 5.0
    DROP_STAGGER = 20.0     # QPointF offset between multiple dropped files

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)

        self.current_zoom  = 1.0
        self._last_pan_pos: QPointF | None = None
        self._on_zoom_changed = None   # optional callback, set by main_window

        self._configure()

    def _configure(self) -> None:
        # ── Frame ─────────────────────────────────────────────────────────────
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setLineWidth(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.viewport().setContentsMargins(0, 0, 0, 0)

        # ── Scrollbars ────────────────────────────────────────────────────────
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ── Transform anchors ─────────────────────────────────────────────────
        # NoAnchor — we control camera position explicitly, Qt does not help.
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # ── Paint quality ─────────────────────────────────────────────────────
        # MinimalViewportUpdate: only repaints dirty regions.  During pan, Qt
        # uses a bitblt scroll (very cheap) plus repaints only the newly-exposed
        # strip — no full-viewport repaint on every mouse-move tick.
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing)

        # ── Focus ─────────────────────────────────────────────────────────────
        # NoFocus prevents the view from stealing keyboard focus from toolbar
        # widgets. Key events are routed explicitly when needed.
        self.setFocusPolicy(Qt.NoFocus)

        # ── Drag and drop ─────────────────────────────────────────────────────
        self.setAcceptDrops(True)

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect) -> None:
        """Solid canvas background — one honest rectangle, no magic yet."""
        painter.save()
        painter.resetTransform()
        painter.fillRect(self.viewport().rect(), QColor(Theme.backDrop))
        painter.restore()

    def drawForeground(self, painter: QPainter, rect) -> None:
        """Rounded border overlaying the viewport edges — matches node bevel style."""
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing)

        vr = self.viewport().rect()
        radius = Theme.nodeRoundRadius
        bw = Theme.nodeBorderWidth

        outer = QPainterPath()
        outer.addRoundedRect(vr.adjusted(0, 0, 0, 0), radius, radius)

        # Paint the four corner slivers (outside the rounded rect) with the
        # window background so nodes dragged near the edge don't bleed through.
        full = QPainterPath()
        full.addRect(vr)
        corners = full.subtracted(outer)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Theme.windowBg))
        painter.drawPath(corners)

        # Border strip — drawn on top of the corners.
        inner = QPainterPath()
        inner.addRoundedRect(
            vr.adjusted(bw, bw, -bw, -bw),
            max(0, radius - bw), max(0, radius - bw),
        )
        border_strip = outer.subtracted(inner)

        painter.setBrush(QColor(Theme.primaryBorder))
        painter.drawPath(border_strip)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_zoom(self, factor: float, anchor: QPointF | None = None) -> None:
        """
        Apply a zoom factor clamped to [ZOOM_MIN, ZOOM_MAX].
        If anchor is provided the scene point under that position stays fixed.
        """
        new_zoom = self.current_zoom * factor
        if not (self.ZOOM_MIN <= new_zoom <= self.ZOOM_MAX):
            return

        if anchor is not None:
            old_vp = self.mapFromScene(anchor)
            self.scale(factor, factor)
            new_vp = self.mapFromScene(anchor)
            delta  = new_vp - old_vp
            zoom   = self.transform().m11()
            self.translate(-delta.x() / zoom, -delta.y() / zoom)
        else:
            self.scale(factor, factor)

        self.current_zoom = new_zoom
        if self._on_zoom_changed:
            self._on_zoom_changed()

    def wheelEvent(self, event) -> None:
        """Zoom anchored to the cursor position."""
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        anchor = self.mapToScene(event.position().toPoint())
        self._apply_zoom(factor, anchor=anchor)
        event.accept()

    def mousePressEvent(self, event) -> None:
        """Start pan on middle mouse. Route clicks when a floating wire is active."""
        self.setFocus()
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = event.position()
            self.setRenderHint(QPainter.Antialiasing, False)
            event.accept()
            return
        scene = self.scene()
        if scene and getattr(scene, '_floating_conn', None):
            if event.button() == Qt.RightButton:
                scene.cancel_connection()
                event.accept()
                return
            if event.button() == Qt.LeftButton:
                scene_pos = self.mapToScene(event.position().toPoint())
                # Use items() not itemAt() — itemAt can return the parent node
                # instead of the Port child when they share the same area
                from nodes.Port import Port
                input_port = next(
                    (i for i in scene.items(scene_pos)
                     if isinstance(i, Port) and not i.is_output),
                    None
                )
                if input_port:
                    scene.complete_connection(input_port.parent_node,
                                              explicit_port=input_port)
                else:
                    # No port hit — snap to the closest input port on whatever
                    # node is under the cursor; dynamic corner routing handles the rest
                    node = next(
                        (i for i in scene.items(scene_pos)
                         if hasattr(i, 'input_ports') and i.input_ports),
                        None
                    )
                    if node:
                        scene.complete_connection(node)
                    else:
                        scene.cancel_connection()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Pan on middle mouse drag; update floating wire on move."""
        if self._last_pan_pos is not None and event.buttons() & Qt.MiddleButton:
            delta          = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            zoom           = self.transform().m11()
            self.translate(delta.x() / zoom, delta.y() / zoom)
            event.accept()
            return
        scene = self.scene()
        if scene and getattr(scene, '_floating_conn', None):
            scene_pos = self.mapToScene(event.position().toPoint())
            scene.update_floating_connection(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """End pan; expand the scene rect if a node was dragged outside it."""
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = None
            self.setRenderHint(QPainter.Antialiasing, True)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            # Defer to next event loop tick — scene state is fully settled by then
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._expand_scene_rect)

    # ── Scene auto-expansion ──────────────────────────────────────────────────

    _EXPAND_MARGIN = 300   # breathing room (scene px) beyond the outermost node

    def _expand_scene_rect(self) -> None:
        """
        Grow the scene rect to encompass all nodes plus _EXPAND_MARGIN padding.
        Only measures nodes (not wires) — wire paths overshoot into nodes and
        would inflate the rect incorrectly.  Never shrinks; uses united().
        """
        scene = self.scene()
        if not scene:
            return
        from PySide6.QtCore import QRectF
        nodes_rect = QRectF()
        for item in scene.items():
            if hasattr(item, 'data') and hasattr(item, 'rect'):
                nodes_rect = nodes_rect.united(item.mapRectToScene(item.rect()))
        if nodes_rect.isNull():
            return
        m = self._EXPAND_MARGIN
        new_rect = scene.sceneRect().united(nodes_rect.adjusted(-m, -m, m, m))
        if new_rect != scene.sceneRect():
            scene.setSceneRect(new_rect)

    # ─────────────────────────────────────────────────────────────────────────
    # DRAG AND DROP
    # ─────────────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        """Accept drags that contain at least one supported image file."""
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(Path(p).suffix.lower() in _IMAGE_EXTENSIONS for p in paths):
                event.acceptProposedAction()
                return
        # Let Qt route internal drags (e.g. palette swatches) to proxy widgets.
        if event.mimeData().hasFormat("application/x-intricate-palette-color"):
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Keep accepting during the drag so the cursor stays correct."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-intricate-palette-color"):
            super().dragMoveEvent(event)
            return

    def dropEvent(self, event) -> None:
        """
        Map the drop position to scene coordinates and create ImageNodes.

        Multiple files are staggered by DROP_STAGGER so they don't pile up.
        Non-image files in a multi-file drop are silently skipped.
        """
        if event.mimeData().hasFormat("application/x-intricate-palette-color"):
            super().dropEvent(event)
            return
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        # Map drop viewport position → scene coordinates (QPointF all the way)
        drop_scene_pos = self.mapToScene(event.position().toPoint())

        offset = QPointF(0.0, 0.0)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            scene = self.scene()
            if scene and hasattr(scene, 'add_image_node'):
                scene.add_image_node(
                    pos  = drop_scene_pos + offset,
                    path = path
                )
                offset += QPointF(self.DROP_STAGGER, self.DROP_STAGGER)

        event.acceptProposedAction()


# Theme import at bottom — View.py is part of the graphics package and
# Theme lives there too. Deferred to avoid any circular import risk at
# package initialisation time.
from .Theme import Theme
from pathlib import Path
