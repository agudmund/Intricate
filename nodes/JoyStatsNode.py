#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/JoyStatsNode.py JoyStatsNode class
-Live debug display for the joy tamagotchi system timers and state for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.NodeData import NodeData
from pretty_widgets.graphics.Theme import Theme


class JoyStatsNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = False
    """
    Live debug display for the joy tamagotchi system.

    Reads all joy state from the main window every second and paints
    a compact stats grid. No custom data — pure read-only display.
    """

    def __init__(self, data: NodeData | None = None):
        if data is None:
            data = NodeData(node_type="joy_stats", title="Joy Stats",
                            width=240.0, height=280.0)
        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()

        # 1-second poll — matches the happy accumulator tick rate
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    def _refresh(self) -> None:
        try:
            self.update()
        except RuntimeError:
            self._poll_timer.stop()

    def _get_window(self):
        """Reach the IntricateApp main window from the scene graph."""
        scene = self.scene()
        if not scene:
            return None
        views = scene.views()
        if not views:
            return None
        return views[0].window()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r   = self.rect()
        pad = self._CONTENT_PAD
        top = self._content_top()

        # Title
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Joy Stats",
        )

        # Body — live stats
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.85)
        y = r.top() + self._body_top()
        line_h = 17

        win = self._get_window()
        if win is None:
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop, "no window")
            painter.restore()
            return

        # Collect all joy state
        bar_val       = getattr(win, 'joy_bar', None)
        bar_pct       = bar_val.value() if bar_val else 0
        sleeping      = getattr(win, '_joy_sleeping', False)
        in_grace      = getattr(win, '_joy_in_grace', False)
        grace_remain  = getattr(win, '_joy_grace_remaining', 0.0)
        happy_secs    = getattr(win, '_joy_happy_secs', 0.0)
        bucket_count  = getattr(win, '_joy_bucket_count', 0)
        bucket_target = getattr(win, '_JOY_BUCKET_SECS', 3600)
        hungry        = getattr(win, '_joy_hungry', False)
        feed_ts       = getattr(win, '_feed_timestamps', [])
        feed_max      = getattr(win, '_FEED_MAX', 3)
        feed_window   = getattr(win, '_FEED_WINDOW', 600.0)
        depl_timer    = getattr(win, '_joy_timer', None)
        depl_interval = depl_timer.interval() if depl_timer else 0
        grace_total   = getattr(win, '_JOY_GRACE_SECS', 600)

        # State string
        if sleeping:
            state = "Sleeping"
            state_color = "#6688aa"
        elif in_grace:
            state = "In Grace"
            state_color = "#7ab88a"
        elif hungry:
            state = "Hungry!"
            state_color = "#d87a7a"
        else:
            state = "Awake"
            state_color = "#b8b872"

        # Count active feeds in window + time until next slot opens
        now = time.monotonic()
        active_in_window = [t for t in feed_ts if now - t < feed_window]
        active_feeds = len(active_in_window)
        if active_feeds >= feed_max and active_in_window:
            # Oldest feed in window — time until it expires and a slot opens
            oldest = min(active_in_window)
            reset_secs = int(feed_window - (now - oldest))
            feed_reset = f"  (reset {reset_secs}s)"
        else:
            feed_reset = ""

        # Draw stats
        lines = [
            (f"Bar:  {bar_pct}%", None),
            (f"State:  {state}", state_color),
            ("", None),
            (f"Grace:  {int(grace_remain)}s / {int(grace_total)}s", None),
            (f"Happy:  {int(happy_secs)}s / {int(bucket_target)}s", None),
            (f"Buckets:  {bucket_count}", None),
            ("", None),
            (f"Depletion:  {depl_interval / 1000:.0f}s per tick", None),
            (f"Feeds:  {active_feeds}/{feed_max}{feed_reset}", None),
            (f"Hungry:  {'yes' if hungry else 'no'}", "#d87a7a" if hungry else None),
        ]

        for text, color in lines:
            if not text:
                y += line_h * 0.4
                continue
            if color:
                painter.setPen(QColor(color))
            else:
                painter.setPen(QColor(Theme.nodeFontColor))
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop, text)
            y += line_h

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        try:
            self._poll_timer.timeout.disconnect(self._refresh)
        except (RuntimeError, TypeError):
            pass
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'JoyStatsNode':
        nd = NodeData(
            node_type="joy_stats", title="Joy Stats",
            uuid=data.get("uuid", ""),
            x=float(data.get("x", 0.0)), y=float(data.get("y", 0.0)),
            width=float(data.get("width", 240.0)), height=float(data.get("height", 280.0)),
            z_value=float(data.get("z_value", 0.0)),
            ports_visible=data.get("ports_visible", False),
            shelf_visible=data.get("shelf_visible", True),
        )
        return JoyStatsNode(nd)
