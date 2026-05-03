#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/PerfNode.py PerfNode class
-Live UI performance HUD — chromeless, pinnable. Times every paint lap the Qt event loop takes, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, QObject, QEvent, QRectF
from PySide6.QtGui import QPainter, QColor, QPen

from nodes.ChromelessRoot import ChromelessRoot
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


class PerfNode(ChromelessRoot):
    """
    Live UI performance monitor — chromeless HUD, fourth descendant of
    ChromelessRoot (after StickerNode, JoyStatsNode, ValueNode).

    Installs a transparent event filter on the graphics view's viewport
    to time the interval between consecutive Qt paint events. All readings
    update on a fast poll timer and render directly onto the node canvas.

    Migrated 2026-05-02 from BaseNode → ChromelessRoot so the node can
    be pinned to the viewport and stay readable at any zoom altitude
    (including aerial). The visual identity stays the same — dark teal
    body, cream border, Lombardi Lake header — only the category changes.

    Readings:
        FPS     — frames per second derived from rolling average frame time
        Last    — most recent inter-frame interval in ms
        Avg     — rolling average over the last 120 samples
        Min/Max — extremes of the current window
        Paints  — total paint events since the filter was installed
        Zoom    — current canvas zoom factor

    Never participates in the wire graph.
    """

    # ── Paint constants ─────────────────────────────────────────────────────
    _TITLE_FONT      = "Chandler42"
    _TITLE_STYLE     = "Italic"          # 1843.otf script-italic Medium — see pretty_widgets.utils.fonts
    _TITLE_FONT_BUMP = 6

    _ROW_COUNT       = 8        # FPS, Last, Avg, Min, Max, Samples, Total paints, Zoom

    # ── Generic unpinned resize — opt in to the corner grip ─────────────────
    # User resizes while unpinned to set the frozen screen size on the next pin.
    _UNPINNED_RESIZE_ENABLED = True

    # ── Demolition manifest — crew tears down the poll timer ────────────────
    _demolition_timers = [('_poll_timer', '_refresh')]

    def __init__(self, data: PerfNodeData | None = None):
        is_fresh = data is None
        if data is None:
            data = PerfNodeData()
            # Auto-fit the height to the actual content layout. Saved sessions
            # come in with whatever height they were saved at — including any
            # user resize via the corner grip — so the auto-fit only applies
            # to fresh nodes.
            data.height = self._compute_auto_height()
        super().__init__(data)

        # Preserve the BaseNode-era visual: dark teal body, cream border.
        # Set once at construction; ChromelessRoot has no NodeBehaviour
        # trying to override the brush on hover.
        self.setBrush(QColor(Theme.perfNodeBg))

        self._timer_obj: _PaintTimer | None = None

        # Fast refresh — 100 ms is plenty for human-readable numbers.
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

        # First-paint event-filter install if we're already in a scene
        # (e.g. session restore — itemChange for SceneHasChanged may have
        # already fired before this constructor ran in unusual paths).
        if self.scene() is not None:
            self._install_filter()

    # ─────────────────────────────────────────────────────────────────────────
    # AUTO-FIT GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    # Footer descender breathing room — Qt's drawText with AlignCenter inside
    # a (line_h)-tall bounding rect centres the baseline, but glyph descenders
    # ('p' in "poll", parens) extend below the baseline and read as touching
    # the bottom border without this padding. 6 px gives the footer text room
    # to breathe against the rounded-rect chrome.
    _FOOTER_BREATHING_PX = 6

    @classmethod
    def _compute_auto_height(cls) -> float:
        """Derive the snug node height from the kit's actual layout values
        at pin_scale=1.0 (fresh nodes are always unpinned).

        Layout from paint(): top pad + header (line_h + 22) + 6 breathing
        + N × (line_h + 3) rows + footer (gap 2 + divider + 6 post + line
        + tail) + footer-descender breathing. Bottom pad rounds the rect
        to the same kit.pad as the top.
        """
        from utils.paint import make_kit
        kit = make_kit(cls._TITLE_FONT, cls._TITLE_STYLE, cls._TITLE_FONT_BUMP)
        header_h = kit.line_h + 22
        rows_h   = cls._ROW_COUNT * (kit.line_h + 3)
        footer_h = kit.line_h + 8
        return float(kit.pad * 2 + header_h + 6 + rows_h + footer_h
                     + cls._FOOTER_BREATHING_PX)

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
        """Timer slot — force a repaint so stats stay fresh. Orphan-timer
        guard via self.scene() probe, matching the chromeless family pattern."""
        try:
            if self.scene() is None:
                return
        except RuntimeError:
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

    # ─────────────────────────────────────────────────────────────────────────
    # CONTEXT MENU — Reset Stats lives here (no button strip on chromeless)
    # ─────────────────────────────────────────────────────────────────────────

    def _extra_context_menu_items(self, ctx) -> None:
        """Append PerfNode-specific actions to the right-click menu.
        Runs after the root inserts the Pin toggle, so this entry sits below it."""
        reset_action = ctx.addAction("Reset Stats")
        reset_action.triggered.connect(self._reset_stats)

    def _reset_stats(self) -> None:
        if self._timer_obj:
            self._timer_obj.reset()
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        # Filter install/uninstall hooked off ItemSceneChange — survives
        # session switches and ensures the filter follows the node into
        # whatever view it lands in.
        if change == self.GraphicsItemChange.ItemSceneHasChanged and value is not None:
            self._install_filter()
        elif change == self.GraphicsItemChange.ItemSceneChange and value is None:
            # Stop polling and uninstall the filter before scene-leave
            # so the demolition crew has a quiet node to tear down.
            try:
                self._poll_timer.stop()
            except (RuntimeError, AttributeError):
                pass
            self._uninstall_filter()
        return super().itemChange(change, value)

    def _quiet_for_shake(self) -> None:
        """Synchronous quieting before the deferred-remove window. Stops
        the poll timer and uninstalls the viewport event filter so neither
        can dispatch into a node about to vanish. Calls super() to keep
        the root's pin-tracking disconnect."""
        super()._quiet_for_shake()
        try:
            self._poll_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        self._uninstall_filter()

    def _demolition_pre(self) -> None:
        """Type-specific teardown — uninstall the filter ahead of the
        demolition crew's standard sequence. Calls super() for the
        root's viewport-tracking disconnect."""
        super()._demolition_pre()
        self._uninstall_filter()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Full paint pipeline — chromeless root paints nothing, every
        descendant owns its full visual. Order: rounded body fill +
        cream border (preserves the BaseNode-era look), then the stats
        grid via the data-grid kit helpers.

        Layout scale is derived from the rect's height vs the auto-fit
        baseline — a single ratio that captures both user-resize (the
        corner grip while unpinned) AND pin-state scaling, because the
        rect grows with both: K×H_auto when resized to K, then ×z_pin
        when pinned. ``rect.height / H_auto = K × z_pin`` captures both
        in one number. Net effect: when the user makes the HUD bigger,
        fonts grow proportionally with the container. Without this, a
        resized HUD shows default-sized text floating in a big empty
        body, which defeats the point of resizing.
        """
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

        t   = self._timer_obj
        kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP,
                       pin_scale=s)
        r   = self.rect()
        x   = r.x() + kit.pad
        y   = r.y() + kit.pad
        w   = r.width() - kit.pad * 2

        y = draw_header(painter, kit, x, y, w, "Performance")
        y += 6 * s   # breathing room between title and stats — scaled with kit

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
