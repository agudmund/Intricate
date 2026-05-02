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
from PySide6.QtGui import QPainter, QColor

from nodes.BaseNode import BaseNode
from data.HealthNodeData import HealthNodeData
from utils.OSClickMonitor import OSClickMonitor
from pretty_widgets.graphics.Theme import Theme


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
    _has_depth_toggle = True

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

        # ── Video buffer tracking ─────────────────────────────────────────────
        self._video_buf_bytes:      int = 0   # current total across all VideoNodes
        self._video_buf_prev:       int = 0   # previous poll snapshot
        self._video_buf_delta:      int = 0   # change since last poll
        self._video_buf_peak:       int = 0   # high-water mark
        self._video_node_count:     int = 0

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
        # Orphan-timer guard — see BaseNode._timer_slot_alive docstring for
        # the full crash context (0xC0000409 from a dead-wrapper access on
        # non-deterministic shutdown).
        if not self._timer_slot_alive('_poll_timer'):
            return

        self._poll_count += 1
        t0 = time.monotonic()

        try:
            gc.collect()
            from nodes.BaseNode import BaseNode as _BaseNode
            from nodes.StickerNode import StickerNode as _StickerNode
            _NODE_ROOTS = (_BaseNode, _StickerNode)

            try:
                self._living_nodes = sum(
                    1 for obj in gc.get_objects()
                    if isinstance(obj, _NODE_ROOTS)
                )
            except RuntimeError:
                pass

            if self.scene():
                try:
                    self._scene_nodes = sum(
                        1 for item in self.scene().items()
                        if isinstance(item, _NODE_ROOTS)
                    )
                except Exception:
                    self._scene_nodes = 0
            else:
                self._scene_nodes = 0

            self._last_gc_time = time.monotonic() - t0

        except Exception:
            self._last_gc_time = time.monotonic() - t0

        # ── Video buffer census ───────────────────────────────────────────
        self._poll_video_buffers()

        self.update()

        if self.scene() and hasattr(self.scene(), 'set_dirty'):
            self.scene().set_dirty(False)

    # ─────────────────────────────────────────────────────────────────────────
    # VIDEO BUFFER CENSUS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _pixmap_bytes(pix) -> int:
        """Estimate byte footprint of a QPixmap (width × height × depth/8)."""
        if pix is None or pix.isNull():
            return 0
        return pix.width() * pix.height() * pix.depth() // 8

    def _poll_video_buffers(self) -> None:
        """Sum the pixmap memory held by every VideoNode in the scene."""
        scene = self.scene()
        if not scene:
            return

        from nodes.VideoNode import VideoNode

        total = 0
        count = 0
        for item in scene.items():
            if isinstance(item, VideoNode):
                count += 1
                total += self._pixmap_bytes(getattr(item, '_frame_pixmap', None))
                total += self._pixmap_bytes(getattr(item, '_scaled_cache', None))

        self._video_buf_prev  = self._video_buf_bytes
        self._video_buf_bytes = total
        self._video_buf_delta = total - self._video_buf_prev
        self._video_buf_peak  = max(self._video_buf_peak, total)
        self._video_node_count = count

    # ─────────────────────────────────────────────────────────────────────────
    # CLICK MONITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _install_monitor(self) -> None:
        """
        Install the OS-level click monitor.
        Called synchronously on ItemSceneHasChanged — main thread, Qt loop running.
        Idempotent.

        Gated on `[intricate.health] click_monitor` in settings.toml
        (default: on).  The monitor installs a WH_MOUSE_LL low-level
        Windows mouse hook, which delays every mouse event system-wide
        up to LowLevelHooksTimeout (default 200ms) while Windows waits
        for our callback to return on the Qt main thread.  Under any
        main-thread load that causes message-queue pressure (trace
        logging, active paint loop, settlers, etc.) the delay can
        surface as sticky cursor response — but in normal use the cost
        is unnoticeable, and click inspection is exactly the kind of
        thing that's wanted ready-to-hand during the rapid debugging
        sessions where it actually matters. Flip the setting to false
        if a sustained heavy-load scenario surfaces cursor stickiness.
        """
        if self._monitor is not None:
            return
        import shared_braincell.settings as _s
        if not bool(_s.get_nested("intricate", "health", "click_monitor", True)):
            self._last_clicked_type = "click monitor off"
            self._last_clicked_item = "enable in [intricate.health] click_monitor"
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

    _demolition_timers = [('_poll_timer', '_poll_gc')]

    def _demolition_pre(self) -> None:
        self._uninstall_monitor()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        from utils.paint import make_kit, draw_header, draw_rows, draw_footer

        kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP)
        r   = self.rect()
        x   = r.x() + kit.pad
        y   = r.y() + self._anim_top_offset + kit.pad
        w   = r.width() - kit.pad * 2

        y = draw_header(painter, kit, x, y, w, "Intricate Health")

        # ── Row data ──────────────────────────────────────────────────────────
        c_calm = QColor(Theme.healthColorCalm)
        c_warn = QColor(Theme.healthColorWarn)
        c_high = QColor(Theme.healthColorHigh)
        c_text = QColor(Theme.textPrimary)

        delta      = self._living_nodes - self._scene_nodes
        delta_str  = f"+{delta}" if delta > 0 else str(delta)
        node_color = (
            c_high if self._living_nodes >= Theme.healthHighThreshold else
            c_warn if self._living_nodes >= Theme.healthWarnThreshold else
            c_calm
        )
        delta_color = c_warn if delta > 0 else c_calm

        def _fmt_bytes(b: int) -> str:
            if abs(b) < 1024:
                return f"{b} B"
            elif abs(b) < 1024 * 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b / (1024 * 1024):.1f} MB"

        vid_delta_str   = f"+{_fmt_bytes(self._video_buf_delta)}" if self._video_buf_delta > 0 else _fmt_bytes(self._video_buf_delta)
        vid_delta_color = c_warn if self._video_buf_delta > 0 else c_calm

        rows: list[tuple[str, str, QColor]] = [
            ("Living nodes",  str(self._living_nodes),              node_color),
            ("Scene nodes",   str(self._scene_nodes),               node_color),
            ("RAM delta",     delta_str,                             delta_color),
            ("Last click",    self._last_clicked_type,               c_text),
            ("  └ identity",  self._last_clicked_item,               kit.c_label),
            ("GC time",       f"{self._last_gc_time * 1000:.1f}ms",  c_text),
            ("Poll #",        str(self._poll_count),                 kit.c_label),
        ]

        if self._video_node_count > 0:
            rows.extend([
                ("",             "",                                     kit.c_label),
                ("🎬 Videos",    str(self._video_node_count),            c_text),
                ("Vid buffers",  _fmt_bytes(self._video_buf_bytes),      c_text),
                ("Vid Δ/poll",   vid_delta_str,                          vid_delta_color),
                ("Vid peak",     _fmt_bytes(self._video_buf_peak),       kit.c_label),
            ])

        y = draw_rows(painter, kit, x, y, w, rows)

        interval_s     = Theme.healthPollIntervalMs / 1000
        monitor_status = "hook ✅" if self._monitor else "hook ⬜"
        draw_footer(painter, kit, x, y, w,
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
