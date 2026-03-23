#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - widgets/pretty_dialog.py
-PrettyDialog: a modern, theme-driven dialog with 3x3 grid, draggable top bar, curtains/fade, and resize grip.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QLabel, QPushButton, QSizeGrip
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from graphics.Theme import Theme

class PrettyDialog(QDialog):
    def __init__(self, parent=None, title="Dialog", modal=True):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(modal)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(f"background: {Theme.windowBg}; border: {Theme.windowBorderWidth}px solid {Theme.primaryBorder}; border-radius: 10px;")
        self._dragging = False
        self._drag_pos = QPoint()
        self._setup_ui(title)
        self._setup_fade()

    def _setup_ui(self, title):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Top bar (draggable)
        self.top_bar = QWidget(self)
        self.top_bar.setFixedHeight(Theme.handleHeightTop)
        self.top_bar.setStyleSheet(f"background: {Theme.backDrop}; border-top-left-radius: 10px; border-top-right-radius: 10px;")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)
        top_layout.addWidget(QLabel(title, self.top_bar))
        top_layout.addStretch()
        close_btn = QPushButton("✕", self.top_bar)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.reject)
        close_btn.setStyleSheet(f"background: transparent; color: {Theme.textPrimary}; border: none; font-size: 18px;")
        top_layout.addWidget(close_btn)
        self.top_bar.mousePressEvent = self._topbar_mouse_press
        self.top_bar.mouseMoveEvent = self._topbar_mouse_move
        self.top_bar.mouseReleaseEvent = self._topbar_mouse_release
        # Central widget
        self.central = QWidget(self)
        self.central.setStyleSheet(f"background: {Theme.windowBg};")
        # Resize grip (bottom right)
        self.resize_grip = _CornerResizeGrip(self)
        # 3x3 grid: top bar, central, resize grip
        layout.addWidget(self.top_bar, 0, 0, 1, 3)
        layout.addWidget(self.central, 1, 0, 1, 3)
        layout.addWidget(self.resize_grip, 2, 2, 1, 1, alignment=Qt.AlignBottom | Qt.AlignRight)
        layout.setRowStretch(1, 1)
        layout.setColumnStretch(1, 1)

    def _setup_fade(self):
        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_anim.start()

    def _topbar_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _topbar_mouse_move(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _topbar_mouse_release(self, event):
        self._dragging = False
        event.accept()

    def setCentralWidget(self, widget):
        self.central.layout().addWidget(widget) if self.central.layout() else self.central.setLayout(QVBoxLayout()) or self.central.layout().addWidget(widget)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Optionally paint a fade/curtain effect here if desired

class _CornerResizeGrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.SizeFDiagCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(Theme.primaryBorder)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        # Draw a simple triangle in the corner
        points = [self.rect().bottomRight(), self.rect().bottomLeft(), self.rect().topRight()]
        painter.drawPolygon(points)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._orig_size = self.parentWidget().size()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            diff = event.globalPosition().toPoint() - self._drag_pos
            new_size = self._orig_size
            new_width = max(100, new_size.width() + diff.x())
            new_height = max(100, new_size.height() + diff.y())
            self.parentWidget().resize(new_width, new_height)
            event.accept()
