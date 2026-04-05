#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/NodeButton.py NodeButton class
-A small action button that lives on a node. Scene-native, LOD-aware for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsObject
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPixmap, QColor

from graphics.Theme import Theme


# Display size in logical pixels — source icons are 2x (32×32) for crispness
BUTTON_SIZE     = 32.0
CONFIRM_TIMEOUT = 2000      # ms — how long the confirm state holds before reset
LOD_THRESHOLD   = 0.4       # Below this zoom the buttons disappear


class NodeButton(QGraphicsObject):
    """
    A small circular action button living directly in scene space as a
    child of a BaseNode.

    Owns two visual states:
        Normal  — the default icon, always shown when LOD permits
        Confirm — swapped in on first click, signals "are you sure?"

    Two-stage delete contract:
        First click  → enters confirm state, starts reset timer
        Second click → executes the callback, resets to normal
        No second click within CONFIRM_TIMEOUT → resets to normal silently

    If only one pixmap is provided (no confirm state needed) the callback
    fires on the first click directly — for non-destructive actions.

    LOD gating:
        Buttons hide themselves when the scene's view zoom drops below
        LOD_THRESHOLD. They reappear automatically when zoomed back in.
        Checked in paint — no timer, no signal, zero overhead.

    Icon spec:
        High-res PNG (1024×1024) with alpha channel.
        Source pixmap kept at full resolution — the painter scales it
        into the BUTTON_SIZE bounding rect with SmoothPixmapTransform,
        so icons stay crisp at every zoom level just like the emoji button.
    """

    def __init__(
        self,
        parent,
        pixmap_normal:  QPixmap,
        callback,
        pixmap_confirm: QPixmap | None = None,
        toggle:         bool           = False,
    ):
        super().__init__(parent)

        self._callback       = callback
        self._toggle         = toggle
        self._in_confirm     = False
        self._reset_timer    = QTimer()
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(CONFIRM_TIMEOUT)
        self._reset_timer.timeout.connect(self._reset)

        # Keep full-res source pixmaps — the painter scales them into the
        # bounding rect at paint time so icons stay crisp at every zoom level,
        # matching the emoji button which renders vector text.
        self._pix_normal  = pixmap_normal
        self._pix_confirm = pixmap_confirm

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, BUTTON_SIZE, BUTTON_SIZE)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # LOD gate — hide at low zoom, no overhead below threshold
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod < LOD_THRESHOLD:
            return

        pix = (
            self._pix_confirm
            if self._in_confirm and self._pix_confirm
            else self._pix_normal
        )
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(self.boundingRect().toRect(), pix)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        if self._pix_confirm is None:
            # Single-stage action — fire immediately
            self._callback()
        elif self._toggle:
            # Persistent toggle — flip state and fire, no timer
            self._in_confirm = not self._in_confirm
            self.update()
            self._callback()
        elif not self._in_confirm:
            # First click — enter confirm state, start reset timer
            self._in_confirm = True
            self._reset_timer.start()
            self.update()
        else:
            # Second click — confirmed, execute
            self._reset()
            self._callback()

        event.accept()

    def _reset(self) -> None:
        """Return to normal state — called by timer or after execution."""
        self._reset_timer.stop()
        self._in_confirm = False
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def detach(self) -> None:
        """
        Stop the timer before the button is removed.
        Called by BaseNode._prepare_for_removal via _detach_buttons().
        """
        self._reset_timer.stop()


EMOJI_OVERFLOW = 4.0  # extra height so emoji glyphs don't clip at the bottom


class EmojiButton(QGraphicsObject):
    """A small button that renders the node's current emoji and shuffles on click."""

    def __init__(self, parent, get_emoji, set_emoji):
        super().__init__(parent)
        self._get_emoji = get_emoji
        self._set_emoji = set_emoji
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, BUTTON_SIZE, BUTTON_SIZE + EMOJI_OVERFLOW)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod < LOD_THRESHOLD:
            return
        from PySide6.QtGui import QFont
        painter.setFont(QFont(Theme.healthFontFamily, int(BUTTON_SIZE * 0.7)))
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.drawText(self.boundingRect(), Qt.AlignCenter, self._get_emoji())

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        import random
        from utils.IconPicker import emojiIcons
        self._set_emoji(random.choice(emojiIcons))
        self.update()
        # Repaint the parent node so the title-row emoji updates too
        if self.parentItem():
            self.parentItem().update()
        event.accept()

    def detach(self) -> None:
        pass
