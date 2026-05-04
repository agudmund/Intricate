#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/JoyStatsNode.py JoyStatsNode class
-Live chromeless HUD for the joy tamagotchi system, conformed to the PerfNode visual language for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen

from nodes.ChromelessRoot import ChromelessRoot
from data.JoyStatsNodeData import JoyStatsNodeData
from pretty_widgets.graphics.Theme import Theme
from shared_braincell.logger import setup_logger, TRACE

_log = setup_logger("joy_stats")


class JoyStatsNode(ChromelessRoot):
    """Live HUD for the joy tamagotchi system.

    Reads joy state from the main window every second and paints a
    compact stats grid: bar percentage, state label, grace countdown,
    happy accumulator, bucket count, depletion rate, feed window,
    hunger flag.

    Chromeless — second descendant of ChromelessRoot (StickerNode was
    the first, PerfNode is the fourth).  Inherits viewport pin (right-
    click to toggle), shake-delete, right-click context menu, and the
    demolition-crew teardown contract.

    Visual language conformed to PerfNode 2026-05-04: dark teal
    `Theme.perfNodeBg` body with a cream `Theme.nodeBorder` outline,
    layout driven by `utils.paint.make_kit` + `draw_header` /
    `draw_rows` / `draw_footer`.  The kit-based draw makes JoyStatsNode
    and PerfNode read as siblings on the canvas — same chrome
    proportions, same dotted dividers, same Lombardi Lake header.
    Pre-this date the node had its own hand-rolled layout with a
    semi-transparent about-family background and no border.

    Never participates in the wire graph.
    """

    # ── Paint constants ─────────────────────────────────────────────────────
    _TITLE_FONT      = "Chandler42"
    _TITLE_STYLE     = "Italic"          # 1843.otf script-italic Medium — see pretty_widgets.utils.fonts
    _TITLE_FONT_BUMP = 6

    # 11 rows total — 9 data rows + 2 visual-spacer rows that group the
    # readings into Current / Accumulators / Feed-state clusters.  Counted
    # together because draw_rows advances by line_h + 3*s for every row
    # regardless of whether it carries text, so the auto-fit needs to
    # account for them all.
    _ROW_COUNT       = 11

    # ── Generic unpinned resize — opt in to the corner grip ─────────────────
    # User resizes while unpinned to set the frozen screen size on the next pin.
    _UNPINNED_RESIZE_ENABLED = True

    # ── Demolition manifest — crew tears down the poll timer ────────────────
    _demolition_timers = [('_poll_timer', '_refresh')]

    # ── Footer descender breathing room ─────────────────────────────────────
    # Same 6-px nudge PerfNode adopts.  draw_footer's AlignCenter inside a
    # line_h-tall rect centres the baseline; descenders ('p' in "poll", parens)
    # extend below the baseline and read as touching the bottom border without
    # this padding.
    _FOOTER_BREATHING_PX = 6

    def __init__(self, data: JoyStatsNodeData | None = None):
        is_fresh = data is None
        if data is None:
            data = JoyStatsNodeData()
            # Auto-fit the height to the actual content layout — same
            # convention PerfNode uses.  Saved sessions come in with
            # whatever height they were saved at (including any user
            # corner-grip resize), so the auto-fit only applies to fresh
            # spawns.
            data.height = self._compute_auto_height()
        super().__init__(data)

        _log.log(TRACE, "[joy-init] JoyStatsNode __init__ entered (uuid=%s, fresh=%s)",
                 getattr(data, 'uuid', '?')[:8], is_fresh)

        # Match the PerfNode body colour explicitly — ChromelessRoot has
        # no NodeBehaviour brushing the body on hover, so a single setBrush
        # at construction holds for the lifetime.
        self.setBrush(QColor(Theme.perfNodeBg))

        # 1-second poll — matches the happy accumulator tick rate.
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

        _log.log(TRACE, "[joy-init] JoyStatsNode __init__ complete (uuid=%s)",
                 getattr(data, 'uuid', '?')[:8])

    # ─────────────────────────────────────────────────────────────────────────
    # AUTO-FIT GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _compute_auto_height(cls) -> float:
        """Derive the snug node height from the kit's actual layout values
        at pin_scale=1.0 (fresh nodes are always unpinned).

        Mirrors PerfNode._compute_auto_height verbatim — the layout
        constants are the same because draw_header / draw_rows /
        draw_footer use the same internal spacing across every kit
        consumer.  Top pad + header (line_h + 22) + 6 px breathing +
        N × (line_h + 3) rows + footer (line_h + 8) + footer-descender
        breathing.  Bottom pad rounds the rect to the same kit.pad
        value used at the top.
        """
        from utils.paint import make_kit
        kit = make_kit(cls._TITLE_FONT, cls._TITLE_STYLE, cls._TITLE_FONT_BUMP)
        header_h = kit.line_h + 22
        rows_h   = cls._ROW_COUNT * (kit.line_h + 3)
        footer_h = kit.line_h + 8
        return float(kit.pad * 2 + header_h + 6 + rows_h + footer_h
                     + cls._FOOTER_BREATHING_PX)

    # ─────────────────────────────────────────────────────────────────────────
    # POLL
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Timer slot — force a repaint so stats stay fresh.  Orphan-timer
        guard via self.scene() probe, matching the chromeless family pattern."""
        _log.log(TRACE, "[joy-refresh] %s tick", self._log_id())
        try:
            if self.scene() is None:
                _log.log(TRACE, "[joy-refresh] %s no scene, skipping", self._log_id())
                return
        except RuntimeError:
            _log.warning("[joy-refresh] %s RuntimeError on scene() — C++ side gone, stopping timer",
                         self._log_id())
            try:
                self._poll_timer.stop()
                self._poll_timer.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
            return
        try:
            self.update()
        except RuntimeError:
            _log.warning("[joy-refresh] %s RuntimeError on update() — stopping timer",
                         self._log_id())
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
        """Full paint pipeline — chromeless root paints nothing, every
        descendant owns its full visual.  Order: rounded body fill +
        cream border (the PerfNode look), then the stats grid via the
        data-grid kit helpers.

        Layout scale derives from rect.height / auto-fit baseline —
        a single ratio that captures both user-resize (corner grip
        while unpinned) AND pin-state scaling.  When the user makes
        the HUD bigger, fonts grow proportionally with the container.
        """
        _log.log(TRACE, "[joy-paint] %s paint() entered (removal_done=%s)",
                 self._log_id(), getattr(self, '_removal_done', '?'))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        h_auto = self._compute_auto_height()
        s      = self.rect().height() / h_auto if h_auto > 0 else 1.0

        radius   = Theme.nodeRoundRadius * s
        border_w = max(1, int(round(Theme.nodeBorderWidth * s)))
        painter.setBrush(self.brush())
        painter.setPen(QPen(QColor(Theme.nodeBorder), border_w))
        painter.drawRoundedRect(self.rect(), radius, radius)

        self._paint_stats(painter, s)
        painter.restore()

    def _paint_stats(self, painter: QPainter, s: float) -> None:
        from utils.paint import make_kit, draw_header, draw_rows, draw_footer

        kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP,
                       pin_scale=s)
        r   = self.rect()
        x   = r.x() + kit.pad
        y   = r.y() + kit.pad
        w   = r.width() - kit.pad * 2

        y = draw_header(painter, kit, x, y, w, "Joy Stats")
        y += 6 * s   # breathing room between title and stats — scaled with kit

        # Reach the running app for live joy state.  Out-of-scene during
        # demolition or session-switch transitions is normal — render a
        # quiet placeholder via the kit fonts and exit early.
        win = self._get_window()
        if win is None:
            painter.setFont(kit.f_label)
            painter.setPen(kit.c_label)
            painter.drawText(int(x), int(y), int(w), kit.line_h * 3,
                             Qt.AlignCenter, "no window")
            return

        # ── Collect joy state ────────────────────────────────────────────
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
        feed_cooldown = getattr(win, '_FEED_COOLDOWN', 60.0)
        last_feed_t   = getattr(win, '_last_feed_time', 0.0)
        depl_timer    = getattr(win, '_joy_timer', None)
        depl_interval = depl_timer.interval() if depl_timer else 0
        grace_total   = getattr(win, '_JOY_GRACE_SECS', 600)

        # ── Status colours ───────────────────────────────────────────────
        # Joy state has its own emotional palette — keep the existing
        # hexes rather than swapping for healthColorCalm/Warn/High, since
        # "Sleeping / In Grace / Hungry / Awake" are mood reads, not
        # threshold reads.  The bar-percentage and hungry-flag rows DO
        # use the standard health threshold palette since they're
        # quantitative.
        c_calm = QColor(Theme.healthColorCalm)
        c_warn = QColor(Theme.healthColorWarn)
        c_high = QColor(Theme.healthColorHigh)
        c_text = QColor(Theme.textPrimary)

        if sleeping:
            state, state_color = "Sleeping", QColor("#6688aa")
        elif in_grace:
            state, state_color = "In Grace", QColor("#7ab88a")
        elif hungry:
            state, state_color = "Hungry!", QColor("#d87a7a")
        else:
            state, state_color = "Awake",   QColor("#b8b872")

        # Bar colour — quantitative threshold read (high / warn / low)
        bar_color = c_calm if bar_pct >= 70 else c_warn if bar_pct >= 30 else c_high

        # Active feeds in window + reset countdown if capped
        now = time.monotonic()
        active_in_window = [t for t in feed_ts if now - t < feed_window]
        active_feeds = len(active_in_window)
        if active_feeds >= feed_max and active_in_window:
            oldest = min(active_in_window)
            reset_secs = int(feed_window - (now - oldest))
            feeds_value = f"{active_feeds}/{feed_max} (reset {reset_secs}s)"
        else:
            feeds_value = f"{active_feeds}/{feed_max}"

        # Next-feed-available countdown — the binding constraint is whichever
        # of (per-feed cooldown, window-cap reset) has more time remaining.
        # Both are 0 when neither gate is active → feed available "now".
        # Updated every poll tick (1 s) so the value ticks down live.
        cooldown_remaining = max(0.0, feed_cooldown - (now - last_feed_t))
        if active_feeds >= feed_max and active_in_window:
            window_remaining = max(0.0, feed_window - (now - min(active_in_window)))
        else:
            window_remaining = 0.0
        next_feed_secs = max(cooldown_remaining, window_remaining)
        if next_feed_secs > 0.5:
            next_feed_value = f"{int(next_feed_secs)}s"
            next_feed_color = kit.c_label
        else:
            next_feed_value = "now"
            next_feed_color = c_calm

        hungry_color = c_high if hungry else kit.c_label

        # ── Rows — three logical clusters separated by empty-row spacers ──
        # Empty ("", "", _) rows draw nothing visible but advance the y
        # cursor by line_h + 3*s (draw_rows does this unconditionally).
        # Total row count is _ROW_COUNT = 10, accounted for in the
        # auto-fit calculation.
        rows: list[tuple[str, str, QColor]] = [
            ("Bar",        f"{bar_pct}%",                              bar_color),
            ("State",      state,                                       state_color),
            ("",           "",                                          c_text),
            ("Grace",      f"{int(grace_remain)}s / {int(grace_total)}s", c_text),
            ("Happy",      f"{int(happy_secs)}s / {int(bucket_target)}s", c_text),
            ("Buckets",    str(bucket_count),                            c_text),
            ("",           "",                                          c_text),
            ("Depletion",  f"{depl_interval / 1000:.0f}s per tick",     kit.c_label),
            ("Feeds",      feeds_value,                                  kit.c_label),
            ("Next feed",  next_feed_value,                              next_feed_color),
            ("Hungry",     "yes" if hungry else "no",                    hungry_color),
        ]

        y = draw_rows(painter, kit, x, y, w, rows)
        draw_footer(painter, kit, x, y, w, "1 s poll  ·  happy accumulator")

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _quiet_for_shake(self) -> None:
        """Synchronous quieting before the deferred-remove window.

        Stops the 1-second poll timer so a tick landing between shake-
        fire and removeItem can't dispatch _refresh onto a node that's
        about to vanish.  The demolition crew also tears the timer down
        via _demolition_timers, but that runs AFTER scene-leave; this
        method closes the interim race.
        """
        super()._quiet_for_shake()
        try:
            self._poll_timer.stop()
            _log.log(TRACE, "[joy-quiet] %s _poll_timer stopped", self._log_id())
        except (RuntimeError, AttributeError):
            pass

    def _demolition_pre(self) -> None:
        """Log entry/exit around the teardown so the cross-node-destruction
        incident (2026-04-22) leaves a full paper trail.  super() does the
        pin disconnect; we log around it.  Stack emitted frame-by-frame —
        the Rust logger truncates on embedded newlines."""
        _log.info("[joy-demolish] %s _demolition_pre ENTER", self._log_id())
        for i, frame in enumerate(traceback.format_stack()[-15:]):
            for line in frame.rstrip().splitlines():
                _log.info("[joy-demolish] %s   stack[%02d] %s",
                          self._log_id(), i, line)
        super()._demolition_pre()
        _log.info("[joy-demolish] %s _demolition_pre DONE", self._log_id())

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'JoyStatsNode':
        return JoyStatsNode(JoyStatsNodeData.from_dict(data))
