#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/PerfNode.py PerfNode class
-Live UI performance monitor. Times every paint lap the Qt event loop takes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.PerfNodeData import PerfNodeData
from pretty_widgets.graphics.Theme import Theme


_WINDOW = 120   # rolling frame-time window (samples)


class _PaintTimer(QObject):
    """
    Event filter installed on the view's viewport.

    Intercepts every QEvent.Paint, records the wall-clock time between
    consecutive paints, and accumulates them into a rolling deque.
    Never consumes the event — fully transparent to the paint pipeline.
    """

    def __init__(self, viewport: QObject) -> None:
        super().__init__(viewport)
        self._last_t: float | None = None
        self._samples: deque = deque(maxlen=_WINDOW)
        self._total_paints: int = 0
        viewport.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Paint:
            t = time.perf_counter()
            if self._last_t is not None:
                dt_ms = (t - self._last_t) * 1000.0
                # Ignore stalls > 2 s — those are external freezes, not frame pacing
                if dt_ms < 2000.0:
                    self._samples.append(dt_ms)
            self._last_t = t
            self._total_paints += 1
        return False   # never consume

    def reset(self) -> None:
        self._samples.clear()
        self._last_t = None
        self._total_paints = 0

    # ── Derived stats (safe to call from any thread, read-only) ──────────────

    @property
    def last_ms(self) -> float:
        return self._samples[-1] if self._samples else 0.0

    @property
    def avg_ms(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0

    @property
    def min_ms(self) -> float:
        return min(self._samples) if self._samples else 0.0

    @property
    def max_ms(self) -> float:
        return max(self._samples) if self._samples else 0.0

    @property
    def fps(self) -> float:
        avg = self.avg_ms
        return 1000.0 / avg if avg > 0 else 0.0

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def total_paints(self) -> int:
        return self._total_paints


class PerfNode(BaseNode):
    _has_depth_toggle = True
    """
    Live UI performance monitor.

    Installs a transparent event filter on the graphics view's viewport
    to time the interval between consecutive Qt paint events.  All readings
    update on a fast poll timer and render directly onto the node canvas.

    Readings:
        FPS     — frames per second derived from rolling average frame time
        Last    — most recent inter-frame interval in ms
        Avg     — rolling average over the last 120 samples
        Min/Max — extremes of the current window
        Paints  — total paint events since the filter was installed
    """

    def __init__(self, data: PerfNodeData | None = None):
        if data is None:
            data = PerfNodeData()
        super().__init__(data)
        self.setBrush(QColor(Theme.perfNodeBg))

        self._timer_obj: _PaintTimer | None = None

        # Fast refresh — 100 ms is plenty for human-readable numbers
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # FILTER LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _install_filter(self) -> None:
        if self._timer_obj is not None:
            return
        scene = self.scene()
        if not scene:
            return
        views = scene.views()
        if not views:
            return
        self._timer_obj = _PaintTimer(views[0].viewport())

    def _uninstall_filter(self) -> None:
        if self._timer_obj is None:
            return
        # removeEventFilter cleans up; the QObject parent (viewport) owns it
        vp = self._timer_obj.parent()
        if vp:
            vp.removeEventFilter(self._timer_obj)
        self._timer_obj.deleteLater()
        self._timer_obj = None

    # ─────────────────────────────────────────────────────────────────────────
    # POLL
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        try:
            self.update()
        except RuntimeError:
            self._poll_timer.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        reset_pix = Theme.icon(Theme.iconReset, fallback_color="#7a9aaa")
        self._buttons.append(NodeButton(self, reset_pix, self._reset_stats))

    def _reset_stats(self) -> None:
        if self._timer_obj:
            self._timer_obj.reset()
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if not hasattr(self, '_timer_obj'):
            return super().itemChange(change, value)

        match change:
            case self.GraphicsItemChange.ItemSceneChange if value is None:
                self._poll_timer.stop()
                self._uninstall_filter()
            case self.GraphicsItemChange.ItemSceneHasChanged if value is not None:
                self._install_filter()

        return super().itemChange(change, value)

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        self._uninstall_filter()
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        t = self._timer_obj
        r      = self.rect()
        pad    = 12
        x      = r.x() + pad
        y      = r.y() + self._anim_top_offset + pad
        w      = r.width() - pad * 2
        line_h = 18

        c_label = QColor(Theme.healthColorLabel)
        c_calm  = QColor(Theme.healthColorCalm)
        c_warn  = QColor(Theme.healthColorWarn)
        c_high  = QColor(Theme.healthColorHigh)
        c_text  = QColor(Theme.textPrimary)

        f_label  = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel))
        f_value  = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeValue))
        f_value.setBold(True)
        f_header = QFont(self._TITLE_FONT, max(1, Theme.healthFontSizeHeader + self._TITLE_FONT_BUMP))
        f_header.setStyleName(self._TITLE_STYLE)
        f_footer = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeFooter))

        # ── HEADER ────────────────────────────────────────────────────────────
        painter.setFont(f_header)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        painter.drawText(int(x), int(y), int(w), line_h + 4,
                         Qt.AlignLeft | Qt.AlignVCenter, "Performance")
        y += line_h + 6

        # ── DIVIDER ───────────────────────────────────────────────────────────
        div_pen = QPen(QColor(Theme.primaryBorder), 1, Qt.DotLine)
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 8

        if t is None or t.sample_count == 0:
            painter.setFont(f_label)
            painter.setPen(c_label)
            painter.drawText(int(x), int(y), int(w), line_h * 3,
                             Qt.AlignCenter, "waiting for paint events…")
            return

        fps     = t.fps
        avg     = t.avg_ms
        last    = t.last_ms
        mn      = t.min_ms
        mx      = t.max_ms
        samples = t.sample_count
        total   = t.total_paints

        # Colour-code fps: ≥50 calm, ≥25 warn, <25 hot
        fps_color = c_calm if fps >= 50 else c_warn if fps >= 25 else c_high
        # Frame time colour mirrors fps thresholds (inverse)
        avg_color = c_calm if avg <= 20 else c_warn if avg <= 40 else c_high

        rows: list[tuple[str, str, QColor]] = [
            ("FPS",       f"{fps:.1f}",        fps_color),
            ("Last",      f"{last:.1f} ms",    avg_color),
            ("Avg",       f"{avg:.1f} ms",      avg_color),
            ("Min",       f"{mn:.1f} ms",       c_calm),
            ("Max",       f"{mx:.1f} ms",       c_warn if mx > 40 else c_text),
            ("Samples",   f"{samples}/{_WINDOW}", c_label),
            ("Total paints", str(total),        c_label),
        ]

        for label, value, value_color in rows:
            painter.setFont(f_label)
            painter.setPen(c_label)
            painter.drawText(int(x), int(y), int(w * 0.6), line_h,
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.setFont(f_value)
            painter.setPen(value_color)
            painter.drawText(int(x), int(y), int(w), line_h,
                             Qt.AlignRight | Qt.AlignVCenter, value)
            y += line_h + 3

        # ── FOOTER ───────────────────────────────────────────────────────────
        y += 2
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 6
        painter.setFont(f_footer)
        painter.setPen(c_label)
        painter.drawText(int(x), int(y), int(w), line_h,
                         Qt.AlignCenter, "100 ms poll  ·  120-frame window")

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PerfNode':
        return PerfNode(PerfNodeData.from_dict(data))
