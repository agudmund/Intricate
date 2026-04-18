#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/hover_glow.py hover sparkle effect
-Reusable anticipation-burst hover glow extracted from the Notepad++ Duplex toolbar for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import (
    QObject, QEvent, Property,
    QPropertyAnimation, QSequentialAnimationGroup, QEasingCurve,
)
from PySide6.QtGui import QColor
from pretty_widgets.graphics.Theme import Theme


class HoverGlow(QObject):
    """
    Installable hover sparkle for any QWidget.

    Drives a 4-phase color animation on enter (dip → hold → burst → settle)
    and a single smooth fade on leave.

    Three modes:

    1. **Button mode** (default) — pass a *base_style*; the glow appends
       ``QPushButton { color: …; }`` on each frame.

    2. **Template mode** — pass a *style_template* with ``{color}``
       placeholders; the glow formats the full stylesheet each frame.

    3. **Callback mode** — pass an *apply_fn(color_hex)* callable; the
       glow calls it with the hex color string on each frame.  Use this
       when the target needs custom logic (e.g. tinting a pixmap).

    Usage:
        HoverGlow.install(btn, base_style="QPushButton { background: #1a1a1a; }")
        HoverGlow.install(slider, apply_fn=slider.set_handle_tint, rest_color=Theme.primaryBorder)

    The returned HoverGlow is parented to the widget so it shares its lifetime.
    """

    # ── Timing — matches the refined Notepad++ Duplex toolbar feel ────────────
    DIP_MS    = 197   # anticipation — fade down
    HOLD_MS   =  57   # hold breath at dip color
    BURST_MS  =   1   # burst to gold — single frame ceiling tap
    SETTLE_MS = 195   # settle to final white  (total enter ≈ 450ms)
    LEAVE_MS  = 600   # fade back to resting ivory

    DIP_COLOR  = "#9e9d9b"   # subtle held breath
    GOLD_COLOR = "#dbd3ba"   # barely-there warm sparkle

    def __init__(self, widget, rest_color=None, apply_fn=None, parent=None):
        super().__init__(parent or widget)
        self._widget = widget
        self._base_style = ""
        self._style_template = ""
        self._apply_fn = apply_fn
        self._rest_color = rest_color or Theme.textPrimary
        self._color = QColor(self._rest_color)

        # ── Enter: dip → hold → burst → settle ──────────────────────────────
        self._phase1 = QPropertyAnimation(self, b"glowColor", self)
        self._phase1.setDuration(self.DIP_MS)
        self._phase1.setEasingCurve(QEasingCurve.Type.InQuint)

        self._hold = QPropertyAnimation(self, b"glowColor", self)
        self._hold.setDuration(self.HOLD_MS)
        self._hold.setStartValue(QColor(self.DIP_COLOR))
        self._hold.setEndValue(QColor(self.DIP_COLOR))

        self._phase2 = QPropertyAnimation(self, b"glowColor", self)
        self._phase2.setDuration(self.BURST_MS)
        self._phase2.setEasingCurve(QEasingCurve.Type.OutQuart)

        self._phase3 = QPropertyAnimation(self, b"glowColor", self)
        self._phase3.setDuration(self.SETTLE_MS)
        self._phase3.setEasingCurve(QEasingCurve.Type.InQuad)

        self._enter_anim = QSequentialAnimationGroup(self)
        self._enter_anim.addAnimation(self._phase1)
        self._enter_anim.addAnimation(self._hold)
        self._enter_anim.addAnimation(self._phase2)
        self._enter_anim.addAnimation(self._phase3)

        # ── Leave: smooth fade back ──────────────────────────────────────────
        self._leave_anim = QPropertyAnimation(self, b"glowColor", self)
        self._leave_anim.setDuration(self.LEAVE_MS)
        self._leave_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        widget.installEventFilter(self)

    # ── Animated color property ──────────────────────────────────────────────

    def _get_color(self) -> QColor:
        return self._color

    def _set_color(self, color: QColor) -> None:
        self._color = color
        self._apply_color()

    glowColor = Property(QColor, _get_color, _set_color)

    def _apply_color(self):
        """Push the animated color to the widget via the active mode."""
        hex_color = self._color.name()
        if self._apply_fn:
            self._apply_fn(hex_color)
        elif self._style_template:
            self._widget.setStyleSheet(self._style_template.format(color=hex_color))
        else:
            self._widget.setStyleSheet(
                self._base_style + f" QPushButton {{ color: {hex_color}; }}"
            )

    # ── Event filter — enter / leave ─────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is not self._widget:
            return False

        if event.type() == QEvent.Type.Enter:
            self._enter_anim.stop()
            self._leave_anim.stop()
            self._phase1.setStartValue(QColor(self._color))
            self._phase1.setEndValue(QColor(self.DIP_COLOR))
            self._phase2.setStartValue(QColor(self.DIP_COLOR))
            self._phase2.setEndValue(QColor(self.GOLD_COLOR))
            self._phase3.setStartValue(QColor(self.GOLD_COLOR))
            self._phase3.setEndValue(QColor(Theme.buttonTextHover))
            self._enter_anim.start()

        elif event.type() == QEvent.Type.Leave:
            self._enter_anim.stop()
            self._leave_anim.stop()
            self._leave_anim.setStartValue(QColor(self._color))
            self._leave_anim.setEndValue(QColor(self._rest_color))
            self._leave_anim.start()

        return False

    # ── Public API ───────────────────────────────────────────────────────────

    def set_base_style(self, style: str):
        """Store the widget's base stylesheet (everything except color)."""
        self._base_style = style

    @classmethod
    def install(cls, widget, base_style: str = "", style_template: str = "",
                apply_fn=None, rest_color=None) -> "HoverGlow":
        """Attach a hover glow to *widget* and return the HoverGlow instance.

        *base_style* — the widget's stylesheet minus the color rule (button mode).
        *style_template* — full stylesheet with ``{color}`` placeholders (template mode).
        *apply_fn* — callable(color_hex) invoked each frame (callback mode).
        *rest_color* — the color to return to on leave (default: Theme.textPrimary).
        """
        glow = cls(widget, rest_color=rest_color or Theme.textPrimary, apply_fn=apply_fn)
        if style_template:
            glow._style_template = style_template
        elif not apply_fn:
            glow.set_base_style(base_style)
        glow._apply_color()
        return glow
