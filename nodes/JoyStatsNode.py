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
from PySide6.QtWidgets import QGraphicsItem

from nodes.BaseNode import BaseNode
from data.NodeData import NodeData
from data.JoyStatsNodeData import JoyStatsNodeData
from pretty_widgets.graphics.Theme import Theme


class JoyStatsNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = True
    """
    Live debug display for the joy tamagotchi system.

    Reads all joy state from the main window every second and paints
    a compact stats grid. Also pinnable to the viewport — right-click
    toggles the pin; while pinned the node stays in screen-space as
    the canvas pans/zooms underneath it. Same mechanic StickerNode
    uses for viewport-anchored HUD stickers.
    """

    def __init__(self, data: JoyStatsNodeData | None = None):
        if data is None:
            data = JoyStatsNodeData()
        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()

        # Viewport pin state — mirrors StickerNode exactly.
        self._pin_connected = False

        # 1-second poll — matches the happy accumulator tick rate
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

        # Pinned-on-load — re-establish the viewport anchor once the
        # scene/view are fully constructed. Deferred with a zero-delay
        # timer so scene.views() is populated by the time we ask.
        if data.pinned:
            QTimer.singleShot(0, self._activate_pin)

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutTransparency)
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
        # Orphan-timer guard (see BaseNode._timer_slot_alive).
        if not self._timer_slot_alive('_poll_timer'):
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
    # INTERACTION — right-click to pin/unpin
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """Intercept right-click to show the pin context menu.

        BaseNode's default mousePressEvent treats right-click as "begin
        a wire connection" — which never applies to JoyStatsNode (it's
        a HUD node, never wired). So we claim right-click here for the
        pin/unpin action and defer everything else to super().
        """
        if event.button() == Qt.RightButton:
            self._show_context_menu(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def _show_context_menu(self, event) -> None:
        """Right-click menu. Pin toggle is the only action — same chrome
        and vocabulary StickerNode uses (PrettyMenu via pretty_menu)."""
        from pretty_widgets.PrettyMenu import menu as pretty_menu
        ctx = pretty_menu()
        pin_action = ctx.addAction("Pin to Viewport")
        pin_action.setCheckable(True)
        pin_action.setChecked(self.data.pinned)
        pin_action.triggered.connect(self._toggle_pin)
        # Map the scene-space event position to the screen for the menu.
        view = self._get_view()
        if view:
            screen_pos = view.mapToGlobal(
                view.mapFromScene(event.scenePos())
            )
        else:
            screen_pos = event.screenPos()
        ctx.exec(screen_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # VIEWPORT PINNING — mirrors StickerNode's implementation
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        if self.data.pinned:
            self._deactivate_pin()
        else:
            self._activate_pin()

    def _activate_pin(self) -> None:
        """Pin the node to its current viewport position — disable dragging
        and record the viewport-space anchor point."""
        self.data.pinned = True
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        view = self._get_view()
        if view:
            vp_pos = view.mapFromScene(self.pos())
            self.data.pin_vp_x = vp_pos.x()
            self.data.pin_vp_y = vp_pos.y()
            self._connect_viewport_tracking(view)

    def _deactivate_pin(self) -> None:
        """Unpin — node becomes draggable again and moves with the canvas."""
        self.data.pinned = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._disconnect_viewport_tracking()

    def _connect_viewport_tracking(self, view) -> None:
        if self._pin_connected:
            return
        # Primary channel: the view emits viewTransformed on pan/zoom
        # that mutate the transform directly. Scrollbars only fire when
        # the scene rect grows past the viewport — rare, but kept as a
        # backup channel.
        if hasattr(view, 'viewTransformed'):
            view.viewTransformed.connect(self._on_viewport_changed)
        view.horizontalScrollBar().valueChanged.connect(self._on_viewport_changed)
        view.verticalScrollBar().valueChanged.connect(self._on_viewport_changed)
        self._pin_connected = True

    def _disconnect_viewport_tracking(self) -> None:
        if not self._pin_connected:
            return
        view = self._get_view()
        if view:
            if hasattr(view, 'viewTransformed'):
                try:
                    view.viewTransformed.disconnect(self._on_viewport_changed)
                except (RuntimeError, TypeError):
                    pass
            try:
                view.horizontalScrollBar().valueChanged.disconnect(self._on_viewport_changed)
                view.verticalScrollBar().valueChanged.disconnect(self._on_viewport_changed)
            except (RuntimeError, TypeError):
                pass
        self._pin_connected = False

    def _on_viewport_changed(self, _value=None) -> None:
        """Canvas transform moved — remap the node back to its recorded
        viewport coordinate so it stays anchored in screen space."""
        # Destructor/signal race guard — same as StickerNode's 2026-04-18
        # fastfail case: a transform tick landing on a node mid-teardown.
        import shiboken6
        if not shiboken6.isValid(self):
            return
        scene = self.scene()
        if scene is None or getattr(scene, '_bulk_removing', 0) > 0:
            return
        view = self._get_view()
        if not view:
            return
        scene_pos = view.mapToScene(int(self.data.pin_vp_x), int(self.data.pin_vp_y))
        self.setPos(scene_pos)

    def _get_view(self):
        scene = self.scene()
        if scene and scene.views():
            return scene.views()[0]
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_timers = [('_poll_timer', '_refresh')]

    def _demolition_pre(self) -> None:
        """Sever viewport tracking before the main teardown sequence —
        the signal-destructor race is real, see _on_viewport_changed."""
        self._disconnect_viewport_tracking()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'JoyStatsNode':
        return JoyStatsNode(JoyStatsNodeData.from_dict(data))
