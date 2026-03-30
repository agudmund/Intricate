#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Button
-The last of the pretty buttons knew that it could become all that it was destined to be, for enjoying.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QSequentialAnimationGroup, QEasingCurve, Property
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QPushButton
from graphics.Theme import Theme

class PrettyButton(QPushButton):
    """
    A warm and pretty button with its own specific defaults 🌿

    Hover glow: textPrimary → dip (anticipation) → buttonTextHover (burst).
    The brief darkness before the burst is the anticipation beat — makes white feel like a spotlight.
    Leave fades straight back to textPrimary.
    """
    # Tune these to adjust the feel once the effect is confirmed working.
    # Flash is the fast rise to lombardiLake; settle is the weighted drop to hover color.
    HOVER_DIP_MS    = 197  # anticipation — fade down
    HOVER_HOLD_MS   =  57  # hold breath at dip color
    HOVER_BURST_MS  =   1  # burst to gold — single frame ceiling tap
    HOVER_SETTLE_MS = 195  # settle to final white  (total = 450ms)
    HOVER_LEAVE_MS  = 600   # fade back to textPrimary on leave  (total enter = 1200ms)
    HOVER_DIP_COLOR  = "#9e9d9b"  # subtle held breath — halfway between ivory and dark
    HOVER_GOLD_COLOR = "#dbd3ba"  # 80% ivory / 20% gold — barely-there warm sparkle

    def __init__(self, text="yay! 🌿", icon_name=None, parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumWidth(Theme.buttonMinWidth)
        self.setMinimumHeight(Theme.buttonMinHeight)
        if icon_name:
            self.set_pretty_icon(icon_name)

        # ── Animated text color ───────────────────────────────────────────────
        self._text_color = QColor(Theme.textPrimary)

        # Enter: dip (anticipation) → burst to white
        # InQuad on the dip means it barely moves for the first ~300ms then drops
        # sharply at the end — creates a natural "hold then decide" feel without a pause.
        self._phase1  = QPropertyAnimation(self, b"textColor", self)
        self._phase1.setDuration(self.HOVER_DIP_MS)
        self._phase1.setEasingCurve(QEasingCurve.Type.InQuint)

        # Hold keyframe — dip color to dip color, no movement, just held breath
        self._hold    = QPropertyAnimation(self, b"textColor", self)
        self._hold.setDuration(self.HOVER_HOLD_MS)
        self._hold.setStartValue(QColor(self.HOVER_DIP_COLOR))
        self._hold.setEndValue(QColor(self.HOVER_DIP_COLOR))

        self._phase2  = QPropertyAnimation(self, b"textColor", self)
        self._phase2.setDuration(self.HOVER_BURST_MS)
        self._phase2.setEasingCurve(QEasingCurve.Type.OutQuart)

        self._phase3  = QPropertyAnimation(self, b"textColor", self)
        self._phase3.setDuration(self.HOVER_SETTLE_MS)
        self._phase3.setEasingCurve(QEasingCurve.Type.InQuad)

        self._enter_anim = QSequentialAnimationGroup(self)
        self._enter_anim.addAnimation(self._phase1)
        self._enter_anim.addAnimation(self._hold)
        self._enter_anim.addAnimation(self._phase2)
        self._enter_anim.addAnimation(self._phase3)

        # Leave: single smooth fade back to resting ivory
        self._leave_anim = QPropertyAnimation(self, b"textColor", self)
        self._leave_anim.setDuration(self.HOVER_LEAVE_MS)
        self._leave_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Apply our Python-driven styles
        self.update_style()

        font = self.font()
        font.setFamily(Theme.buttonFontFamily)
        font.setPointSize(Theme.buttonFontSize)
        font.setBold(Theme.buttonFontBold)
        self.setFont(font)

    # ── Animated text color property ─────────────────────────────────────────

    def _get_text_color(self) -> QColor:
        return self._text_color

    def _set_text_color(self, color: QColor) -> None:
        self._text_color = color
        # Use QPalette for per-frame color updates — avoids triggering a full
        # stylesheet re-resolve (and repaint flush) on every animation tick.
        palette = self.palette()
        palette.setColor(self.foregroundRole(), color)
        self.setPalette(palette)

    textColor = Property(QColor, _get_text_color, _set_text_color)

    # ── Hover enter / leave ───────────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self._enter_anim.stop()
        self._leave_anim.stop()
        self._phase1.setStartValue(QColor(self._text_color))
        self._phase1.setEndValue(QColor(self.HOVER_DIP_COLOR))
        self._phase2.setStartValue(QColor(self.HOVER_DIP_COLOR))
        self._phase2.setEndValue(QColor(self.HOVER_GOLD_COLOR))
        self._phase3.setStartValue(QColor(self.HOVER_GOLD_COLOR))
        self._phase3.setEndValue(QColor(Theme.buttonTextHover))
        self._enter_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._enter_anim.stop()
        self._leave_anim.stop()
        self._leave_anim.setStartValue(QColor(self._text_color))
        self._leave_anim.setEndValue(QColor(Theme.textPrimary))
        self._leave_anim.start()
        super().leaveEvent(event)

    # ── Icon ──────────────────────────────────────────────────────────────────

    def set_pretty_icon(self, icon_name):
        """Fetches pixmap from Theme and applies it as a QIcon."""
        pixmap = Theme.icon(icon_name)
        if pixmap:
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(Theme.iconSize, Theme.iconSize))

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def update_style(self):
        base_padding = 0
        top_padding = base_padding + Theme.buttonTextVerticalOffset
        bottom_padding = base_padding - Theme.buttonTextVerticalOffset
        top_padding = max(0, top_padding)
        bottom_padding = max(0, bottom_padding)

        border_width = Theme.buttonBorderWidth if Theme.buttonBorderEnabled else 0

        # No QPushButton:hover rule — the animation owns the color entirely.
        color = self._text_color.name() if hasattr(self, "_text_color") else Theme.textPrimary

        self.setStyleSheet(f"""
           QPushButton {{
               background-color: {Theme.buttonBg};
               border: {border_width}px solid {Theme.buttonBorder};
               border-radius: 6px;
               color: {color};
               padding: 5px 1px {bottom_padding}px 10px;
           }}
        """)


def button(
    text: str = None,
    icon_name: str = None,
    parent=None,
    **kwargs
) -> QPushButton:
    """
    Creates a fresh pretty button.
    Now with intelligent property mapping for ToolTips and Icons.
    """
    # 1. Initialize with our new icon support
    btn = PrettyButton(text or "", icon_name=icon_name, parent=parent)

    # 2. Handle ToolTip casing specifically (Designer-friendly)
    if "tooltip" in kwargs:
        btn.setToolTip(kwargs.pop("tooltip"))

    # 3. Handle signal connections
    if "clicked" in kwargs:
        slot = kwargs.pop("clicked")
        if slot:
            btn.clicked.connect(slot)

    # 4. Apply remaining kwargs as setters (e.g., fixedWidth=120)
    for key, value in kwargs.items():
        if not key:
            continue
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(btn, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettyButton has no setter for '{key}' (tried {setter_name})")

    return btn
