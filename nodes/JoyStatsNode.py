#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/JoyStatsNode.py JoyStatsNode class
-Live chromeless HUD for the joy tamagotchi system for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.ChromelessRoot import ChromelessRoot
from data.JoyStatsNodeData import JoyStatsNodeData
from pretty_widgets.graphics.Theme import Theme


class JoyStatsNode(ChromelessRoot):
    """Live HUD for the joy tamagotchi system.

    Reads joy state from the main window every second and paints a
    compact stats grid: bar percentage, state label, grace countdown,
    happy accumulator, bucket count, depletion rate, feed window,
    hunger flag.

    Chromeless — second descendant of ChromelessRoot (StickerNode was
    the first). Inherits viewport pin (right-click to toggle),
    shake-delete, right-click context menu, and the demolition-crew
    teardown contract. Paints its own background + title + stats since
    there's no BaseNode chrome doing it automatically.

    Never participates in the wire graph.
    """

    # ── Paint constants (chromeless — no button zone, simpler layout) ────────
    _ROUND_RADIUS    = 12.0
    _CONTENT_PAD     = 15.0   # horizontal padding for title/body text
    _TITLE_TOP_PAD   = 10.0   # px from node top to title baseline area
    _TITLE_HEIGHT    = 30.0   # vertical allowance for title text
    _BODY_TOP_PAD    = 44.0   # px from node top to first body line
    _LINE_HEIGHT     = 17

    # ── Font family / size bumps (formerly inherited from BaseNode) ─────────
    _TITLE_FONT      = "Chandler42"
    _TITLE_STYLE     = "MediumOblique"
    _TITLE_FONT_BUMP = 6
    _BODY_FONT       = "Lato"
    _BODY_FONT_BUMP  = -1

    def __init__(self, data: JoyStatsNodeData | None = None):
        if data is None:
            data = JoyStatsNodeData()
        super().__init__(data)

        # 1-second poll — matches the happy accumulator tick rate
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # COLOR + REFRESH
    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        """Background fill for the rounded-rect body — reads from the
        About-family theme colour + transparency so it stays readable
        against the canvas while still letting the blur breathe through."""
        c = QColor(Theme.aboutBgColor)
        if c.isValid():
            c.setAlpha(Theme.aboutTransparency)
        return c

    def _refresh(self) -> None:
        """Timer slot — force a repaint so stats stay fresh. Orphan-timer
        guard via self.scene() probe, matching the BaseNode pattern."""
        try:
            if self.scene() is None:
                return
        except RuntimeError:
            # C++ side gone — stop ourselves so we can't fire again.
            try:
                self._poll_timer.stop()
                self._poll_timer.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
            return
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

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Full paint pipeline — background rect, then title + stats
        via paint_content. ChromelessRoot's paint() is empty by design,
        so every descendant owns its own rendering."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        # Rounded rect body so the stats text is readable against the canvas.
        painter.setBrush(self._bg_color())
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), self._ROUND_RADIUS, self._ROUND_RADIUS)
        # Content (title + stats grid)
        self.paint_content(painter)
        painter.restore()

    def paint_content(self, painter: QPainter) -> None:
        r   = self.rect()
        pad = self._CONTENT_PAD

        # Title
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        painter.drawText(
            QRectF(r.left() + pad, r.top() + self._TITLE_TOP_PAD,
                   r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Joy Stats",
        )

        # Body — live stats
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.85)
        y = r.top() + self._BODY_TOP_PAD

        win = self._get_window()
        if win is None:
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop, "no window")
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
            oldest = min(active_in_window)
            reset_secs = int(feed_window - (now - oldest))
            feed_reset = f"  (reset {reset_secs}s)"
        else:
            feed_reset = ""

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
                y += self._LINE_HEIGHT * 0.4
                continue
            if color:
                painter.setPen(QColor(color))
            else:
                painter.setPen(QColor(Theme.nodeFontColor))
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop, text)
            y += self._LINE_HEIGHT

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    # Demolition manifest — the crew reads this and stops/disconnects
    # the poll timer on scene-leave. ChromelessRoot.itemChange hands
    # off to the same crew that BaseNode uses.
    _demolition_timers = [('_poll_timer', '_refresh')]

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'JoyStatsNode':
        return JoyStatsNode(JoyStatsNodeData.from_dict(data))
