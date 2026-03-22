#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/View.py
-The window into the world. Renders the scene, handles navigation.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor


class IntricateView(QGraphicsView):
    """
    The viewport into IntricateScene.

    Responsibilities:
        - Renders the scene with correct transparency and antialiasing
        - Handles pan (middle mouse) and zoom (wheel)
        - Keeps the transform anchor honest so pan/zoom feel correct

    Navigation ledger:
        current_zoom tracks the applied scale factor so zoom limits
        and external sync both have a single source of truth.
    """

    ZOOM_MIN = 0.1
    ZOOM_MAX = 5.0

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)

        self.current_zoom = 1.0
        self._last_pan_pos = None

        self._configure()

    def _configure(self):
        # ── Frame ─────────────────────────────────────────────────────────────
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setLineWidth(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.viewport().setContentsMargins(0, 0, 0, 0)

        # ── Scrollbars ────────────────────────────────────────────────────────
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ── Transform anchors ─────────────────────────────────────────────────
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # ── Transparency ──────────────────────────────────────────────────────
        self.viewport().setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # ── Paint quality ─────────────────────────────────────────────────────
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing)

        # ── Focus ─────────────────────────────────────────────────────────────
        self.setFocusPolicy(Qt.NoFocus)

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def drawBackground(self, painter, rect):
        """Solid canvas background — one honest rectangle, no magic yet."""
        painter.save()
        painter.resetTransform()
        painter.fillRect(self.viewport().rect(), QColor("#282828"))
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_zoom(self, factor: float, anchor_scene_pos=None):
        """
        Apply a zoom factor, clamped to [ZOOM_MIN, ZOOM_MAX].

        anchor_scene_pos: if provided, the zoom anchors on that scene point
        so the point under the cursor stays fixed. If None, zooms from center.
        """
        new_zoom = self.current_zoom * factor
        if not (self.ZOOM_MIN <= new_zoom <= self.ZOOM_MAX):
            return

        if anchor_scene_pos:
            old_pos = self.mapFromScene(anchor_scene_pos)
            self.scale(factor, factor)
            new_pos = self.mapFromScene(anchor_scene_pos)
            delta = new_pos - old_pos
            self.translate(
                self.transform().inverted()[0].m11() * delta.x(),
                self.transform().inverted()[0].m22() * delta.y()
            )
        else:
            self.scale(factor, factor)

        self.current_zoom = new_zoom

    def wheelEvent(self, event):
        """Zoom in/out anchored to the cursor position."""
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        anchor = self.mapToScene(event.position().toPoint())
        self._apply_zoom(factor, anchor_scene_pos=anchor)
        event.accept()

    def mousePressEvent(self, event):
        """Start pan on middle mouse."""
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Pan the canvas on middle mouse drag."""
        if self._last_pan_pos and event.buttons() & Qt.MiddleButton:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            zoom = self.transform().m11()
            self.translate(delta.x() / zoom, delta.y() / zoom)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """End pan."""
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
