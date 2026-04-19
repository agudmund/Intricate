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
from PySide6.QtGui import QPainter, QColor

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
        # Orphan-timer guard (see BaseNode._timer_slot_alive).
        if not self._timer_slot_alive('_poll_timer'):
            return
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
        reset_btn = NodeButton(self, reset_pix, self._reset_stats)
        reset_btn._sticker_shadow = True
        reset_btn.setToolTip("Clear the slate and start counting fresh")
        self._buttons.append(reset_btn)

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

    _demolition_timers = [('_poll_timer', '_refresh')]

    def _demolition_pre(self) -> None:
        self._uninstall_filter()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        from utils.paint import make_kit, draw_header, draw_rows, draw_footer

        t   = self._timer_obj
        kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP)
        r   = self.rect()
        x   = r.x() + kit.pad
        y   = r.y() + self._anim_top_offset + kit.pad
        w   = r.width() - kit.pad * 2

        y = draw_header(painter, kit, x, y, w, "Performance")
        y += 6  # breathing room between title and stats

        if t is None or t.sample_count == 0:
            painter.setFont(kit.f_label)
            painter.setPen(kit.c_label)
            painter.drawText(int(x), int(y), int(w), kit.line_h * 3,
                             Qt.AlignCenter, "waiting for paint events…")
            return

        c_calm = QColor(Theme.healthColorCalm)
        c_warn = QColor(Theme.healthColorWarn)
        c_high = QColor(Theme.healthColorHigh)
        c_text = QColor(Theme.textPrimary)

        fps, avg, last = t.fps, t.avg_ms, t.last_ms
        mn, mx         = t.min_ms, t.max_ms
        samples, total = t.sample_count, t.total_paints

        fps_color = c_calm if fps >= 50 else c_warn if fps >= 25 else c_high
        avg_color = c_calm if avg <= 20 else c_warn if avg <= 40 else c_high

        # Current zoom level from the view
        zoom = 0.0
        scene = self.scene()
        if scene and scene.views():
            zoom = getattr(scene.views()[0], 'current_zoom', 0.0)

        rows: list[tuple[str, str, QColor]] = [
            ("FPS",          f"{fps:.1f}",           fps_color),
            ("Last",         f"{last:.1f} ms",       avg_color),
            ("Avg",          f"{avg:.1f} ms",        avg_color),
            ("Min",          f"{mn:.1f} ms",         c_calm),
            ("Max",          f"{mx:.1f} ms",         c_warn if mx > 40 else c_text),
            ("Samples",      f"{samples}/{_WINDOW}", kit.c_label),
            ("Total paints", str(total),             kit.c_label),
            ("Zoom",         f"{zoom:.2f}×",         c_text),
        ]

        y = draw_rows(painter, kit, x, y, w, rows)
        draw_footer(painter, kit, x, y, w, "100 ms poll  ·  120-frame window")

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PerfNode':
        return PerfNode(PerfNodeData.from_dict(data))
