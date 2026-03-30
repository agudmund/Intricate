#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/View.py IntricateView class
-The window into the world. Renders the scene, handles navigation and OS drops for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


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

        # ── Transparency ──────────────────────────────────────────────────────
        self.viewport().setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # ── Paint quality ─────────────────────────────────────────────────────
        # FullViewportUpdate required with TranslucentBackground —
        # partial updates leave artifacts.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
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

    def wheelEvent(self, event) -> None:
        """Zoom anchored to the cursor position."""
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        anchor = self.mapToScene(event.position().toPoint())
        self._apply_zoom(factor, anchor=anchor)
        event.accept()

    def mousePressEvent(self, event) -> None:
        """Start pan on middle mouse. Cancel floating wire on right-click or empty-space click."""
        self.setFocus()
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
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
                item = scene.itemAt(scene_pos, self.transform())
                from nodes.Port import Port
                if not isinstance(item, Port):
                    scene.cancel_connection()
                    # fall through so click still selects/moves nodes
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
        """End pan."""
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Keep accepting during the drag so the cursor stays correct."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """
        Map the drop position to scene coordinates and create ImageNodes.

        Multiple files are staggered by DROP_STAGGER so they don't pile up.
        Non-image files in a multi-file drop are silently skipped.
        """
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
