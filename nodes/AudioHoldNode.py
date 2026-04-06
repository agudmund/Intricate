#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/AudioHoldNode.py AudioHoldNode class
-Silence placeholder node with adjustable duration for merge sequencing, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QColor, QLinearGradient, QPen

from nodes.BaseNode import BaseNode
from data.AudioHoldNodeData import AudioHoldNodeData
from pretty_widgets.graphics.Theme import Theme

_MAX_HOLD_S = 30.0
_MIN_HOLD_S = 0.1
_PROGRESS_H = 6.0
_PROGRESS_PAD = 8.0


class AudioHoldNode(BaseNode):
    """
    Silence placeholder — pure data, no audio player, no files.

    The MergeNode reads hold_seconds when building the ffmpeg combine
    command and inserts silence via anullsrc. Scrub the progress bar
    to adjust the duration smoothly. Zero resource usage beyond paint.
    """

    _has_depth_toggle = True
    _CONTENT_PAD = 15.0
    _TITLE_FONT = "Chandler42"
    _TITLE_FONT_BUMP = 2
    _BODY_FONT = "My Olivin (Nabana)"
    _BODY_FONT_BUMP = -1
    _TITLE_HEIGHT = 40.0

    def __init__(self, data: AudioHoldNodeData | None = None):
        if data is None:
            data = AudioHoldNodeData()
        super().__init__(data)
        self._scrubbing = False
        self._update_caption()

    def _update_caption(self) -> None:
        dur = self.data.hold_seconds
        self.data.caption = f"Silence {dur:.2f}s"
        self.data.title = self.data.caption

    # ─────────────────────────────────────────────────────────────────────────
    # PROGRESS BAR GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def _progress_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + _PROGRESS_PAD,
            r.bottom() - _PROGRESS_H - _PROGRESS_PAD,
            r.width() * 0.66,
            _PROGRESS_H,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION — scrub adjusts duration
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._progress_rect().contains(event.pos()):
            self._scrubbing = True
            self._scrub_to(event.pos().x())
            event.accept()
            return
        self._scrubbing = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._scrubbing and event.buttons() & Qt.LeftButton:
            self._scrub_to(event.pos().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._scrubbing = False
        super().mouseReleaseEvent(event)

    def _scrub_to(self, x: float) -> None:
        pr = self._progress_rect()
        ratio = max(0.0, min(1.0, (x - pr.left()) / max(1.0, pr.width())))
        new_dur = round(_MIN_HOLD_S + ratio * (_MAX_HOLD_S - _MIN_HOLD_S), 2)
        if abs(new_dur - self.data.hold_seconds) > 0.005:
            self.data.hold_seconds = new_dur
            self._update_caption()
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click toggles shelf — no file browser."""
        super().mouseDoubleClickEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)

        painter.save()
        r   = self.rect()
        pad = self._CONTENT_PAD
        y   = r.top() + self._body_top()
        dur = self.data.hold_seconds

        # Duration display
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setOpacity(0.7)
        painter.setPen(QColor(Theme.textPrimary))
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            f"\u23f8  {dur:.2f}s",
        )

        # Progress bar — filled proportional to duration
        painter.setOpacity(1.0)
        pr = self._progress_rect()
        bar_bg = QColor(Theme.nodeBg).lighter(130)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bar_bg)
        painter.drawRoundedRect(pr, 3, 3)

        ratio = (dur - _MIN_HOLD_S) / (_MAX_HOLD_S - _MIN_HOLD_S)
        fill_rect = QRectF(pr.left(), pr.top(), pr.width() * ratio, pr.height())
        grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
        grad.setColorAt(0.0, QColor("#1e1e1e"))
        grad.setColorAt(0.4, QColor("#5c3e4f"))
        grad.setColorAt(0.7, QColor("#a56a85"))
        grad.setColorAt(1.0, QColor("#d87a9e"))
        painter.setBrush(grad)
        painter.drawRoundedRect(fill_rect, 3, 3)

        # End marker
        painter.setPen(QPen(QColor(Theme.textPrimary), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(
            int(pr.right()), int(pr.top() - 10),
            int(pr.right()), int(pr.bottom() + 10),
        )

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'AudioHoldNode':
        return AudioHoldNode(AudioHoldNodeData.from_dict(data))
