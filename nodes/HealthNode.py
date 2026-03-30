#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/HealthNode.py HealthNode class
-Live system health monitor. Watches the GC and every click at OS level, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import gc
import time
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.HealthNodeData import HealthNodeData
from utils.OSClickMonitor import OSClickMonitor
from graphics.Theme import Theme


class HealthNode(BaseNode):
    """
    A live system health monitor node.

    Polls the Python GC on a configurable interval and displays the current
    node census directly on the canvas.

    Click detection:
        Uses OSClickMonitor — a WH_MOUSE_LL global Windows hook that fires
        on every mouse button press system-wide. Reports what the OS actually
        received the click, not just what Qt thinks it received.

        Classification priority:
            1. Qt scene item   — a QGraphicsItem in our scene
            2. Qt widget       — our process, not a scene item
            3. External        — another process (shows exe name)

        Installed synchronously on ItemSceneHasChanged.
        Uninstalled synchronously on ItemSceneChange departure.
        No timers, no races, no monkey-patching.

    Threading contract:
        All Qt operations happen on the main thread.
        OSClickMonitor installs and fires on the main thread via Qt's
        Win32 message loop. No secondary threads involved.

    Serialization:
        Structural identity only — readings are always live.
    """

    def __init__(self, data: HealthNodeData | None = None):
        if data is None:
            data = HealthNodeData()
        super().__init__(data)

        self.setBrush(QColor(Theme.healthNodeBg))

        # ── Live readings ──────────────────────────────────────────────────────
        self._living_nodes:  int   = 0
        self._scene_nodes:   int   = 0
        self._last_gc_time:  float = 0.0
        self._poll_count:    int   = 0

        # ── Click monitor readings ─────────────────────────────────────────────
        self._last_clicked_type: str = "—"
        self._last_clicked_item: str = "—"
        self._monitor: OSClickMonitor | None = None

        # ── Poll timer ────────────────────────────────────────────────────────
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(Theme.healthPollIntervalMs)
        self._poll_timer.timeout.connect(self._poll_gc)
        self._poll_timer.start()

        self._poll_gc()

    # ─────────────────────────────────────────────────────────────────────────
    # GC CENSUS
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_gc(self) -> None:
        self._poll_count += 1
        t0 = time.monotonic()

        try:
            gc.collect()
            from nodes.BaseNode import BaseNode as _BaseNode

            try:
                self._living_nodes = sum(
                    1 for obj in gc.get_objects()
                    if isinstance(obj, _BaseNode)
                )
            except RuntimeError:
                pass

            if self.scene():
                try:
                    self._scene_nodes = sum(
                        1 for item in self.scene().items()
                        if isinstance(item, _BaseNode)
                    )
                except Exception:
                    self._scene_nodes = 0
            else:
                self._scene_nodes = 0

            self._last_gc_time = time.monotonic() - t0

        except Exception:
            self._last_gc_time = time.monotonic() - t0

        self.update()

        if self.scene() and hasattr(self.scene(), 'set_dirty'):
            self.scene().set_dirty(False)

    # ─────────────────────────────────────────────────────────────────────────
    # CLICK MONITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _install_monitor(self) -> None:
        """
        Install the OS-level click monitor.
        Called synchronously on ItemSceneHasChanged — main thread, Qt loop running.
        Idempotent.
        """
        if self._monitor is not None:
            return
        try:
            self._monitor = OSClickMonitor(self)
            self._monitor.install()
        except OSError as e:
            # Hook installation failed — log to display, degrade gracefully
            self._last_clicked_type = "hook failed"
            self._last_clicked_item = str(e)
            self._monitor = None

    def _uninstall_monitor(self) -> None:
        """
        Remove the OS-level click monitor.
        Called synchronously on departure while Qt loop is still running.
        Idempotent.
        """
        if self._monitor is None:
            return
        self._monitor.uninstall()
        self._monitor = None

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if not hasattr(self, '_monitor'):
            return super().itemChange(change, value)

        match change:
            case self.GraphicsItemChange.ItemSceneChange if value is None:
                self._poll_timer.stop()
                self._uninstall_monitor()

            case self.GraphicsItemChange.ItemSceneHasChanged if value is not None:
                self._install_monitor()

        return super().itemChange(change, value)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        r      = self.rect()
        pad    = 12
        x      = r.x() + pad
        y      = r.y() + pad
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
        f_header = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeHeader))
        f_header.setBold(True)
        f_footer = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeFooter))

        # ── HEADER ────────────────────────────────────────────────────────────
        painter.setFont(f_header)
        painter.setPen(c_text)
        painter.drawText(int(x), int(y), int(w), line_h + 4,
                         Qt.AlignLeft | Qt.AlignVCenter, "🩺  Nodal Health")
        y += line_h + 6

        # ── DIVIDER ───────────────────────────────────────────────────────────
        div_pen = QPen(QColor(Theme.primaryBorder), 1, Qt.DotLine)
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 8

        # ── ROWS ──────────────────────────────────────────────────────────────
        delta      = self._living_nodes - self._scene_nodes
        delta_str  = f"+{delta}" if delta > 0 else str(delta)
        node_color = (
            c_high if self._living_nodes >= Theme.healthHighThreshold else
            c_warn if self._living_nodes >= Theme.healthWarnThreshold else
            c_calm
        )
        delta_color = c_warn if delta > 0 else c_calm

        rows: list[tuple[str, str, QColor]] = [
            ("Living nodes",  str(self._living_nodes),              node_color),
            ("Scene nodes",   str(self._scene_nodes),               node_color),
            ("RAM delta",     delta_str,                             delta_color),
            ("Last click",    self._last_clicked_type,               c_text),
            ("  └ identity",  self._last_clicked_item,               c_label),
            ("GC time",       f"{self._last_gc_time * 1000:.1f}ms",  c_text),
            ("Poll #",        str(self._poll_count),                 c_label),
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

        # ── FOOTER DIVIDER ────────────────────────────────────────────────────
        y += 2
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 6

        # ── FOOTER ───────────────────────────────────────────────────────────
        painter.setFont(f_footer)
        painter.setPen(c_label)
        interval_s      = Theme.healthPollIntervalMs / 1000
        monitor_status  = "hook ✅" if self._monitor else "hook ⬜"
        painter.drawText(int(x), int(y), int(w), line_h,
                         Qt.AlignCenter,
                         f"every {interval_s:.0f}s  ·  {monitor_status}")

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'HealthNode':
        return HealthNode(HealthNodeData.from_dict(data))
