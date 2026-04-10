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

from pretty_widgets.graphics.Theme import Theme


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
        return QRectF(0.0, 0.0, BUTTON_SIZE, BUTTON_SIZE + EMOJI_OVERFLOW)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    # Set True on sticker-style buttons to get dynamic radial shadow
    _sticker_shadow = False
    _sticker_pressed = False   # tactile press state
    _SHADOW_DIST    = 3.0     # px offset for shadow in scene coords
    _PRESS_DIST     = 1.5     # px offset for tactile press — gentle squish
    _SHADOW_OPACITY = 0.55

    def _build_shadow_pixmap(self, pix: QPixmap) -> QPixmap:
        """Dark silhouette from the sticker's alpha — reads as a real shadow."""
        sz = pix.size()
        shadow = QPixmap(sz)
        shadow.fill(QColor(0, 0, 0, 0))
        p = QPainter(shadow)
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        p.fillRect(0, 0, sz.width(), sz.height(), QColor(20, 18, 16))
        p.end()
        return shadow

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
        # Scale up the icon so the visible ring matches emoji glyph size.
        # Sidebar/Pillow icons have transparent padding around the outer ring
        # (~78% fill), so they inflate by ~1/0.78 ≈ 1.28 to compensate.
        # Sticker icons fill edge-to-edge (white border included), so they
        # use a tighter scale to leave breathing room between buttons.
        scale   = 1.0 if self._sticker_shadow else 1.28
        scaled  = BUTTON_SIZE * scale
        inset   = (BUTTON_SIZE - scaled) / 2.0
        draw_rect = QRectF(inset, EMOJI_OVERFLOW + inset, scaled, scaled)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Dynamic radial shadow — radiates outward from canvas view centre
        if self._sticker_shadow and self.scene():
            import math
            views = self.scene().views()
            if views:
                view = views[0]
                vp_centre = view.mapToScene(
                    view.viewport().rect().center()
                )
                btn_centre = self.mapToScene(self.boundingRect().center())
                dx = btn_centre.x() - vp_centre.x()
                dy = btn_centre.y() - vp_centre.y()
                length = math.sqrt(dx * dx + dy * dy)
                if length > 1.0:
                    nx, ny = dx / length, dy / length
                else:
                    nx, ny = 0.0, 1.0
                sd = self._SHADOW_DIST / lod  # compensate for zoom

                if self._sticker_pressed:
                    # Pressed — icon shifts partway toward shadow, gentle squish
                    pd = self._PRESS_DIST / lod
                    draw_rect = draw_rect.translated(nx * pd, ny * pd)
                else:
                    # Normal — dark silhouette shadow on the outside edge
                    if not hasattr(self, '_shadow_pix') or self._shadow_pix is None or self._shadow_pix_source is not pix:
                        self._shadow_pix = self._build_shadow_pixmap(pix)
                        self._shadow_pix_source = pix
                    shadow_rect = draw_rect.translated(nx * sd, ny * sd)
                    painter.setOpacity(self._SHADOW_OPACITY)
                    painter.drawPixmap(shadow_rect.toRect(), self._shadow_pix)
                    painter.setOpacity(1.0)

        painter.drawPixmap(draw_rect.toRect(), pix)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        # Tactile press — icon shifts into shadow position
        if self._sticker_shadow:
            self._sticker_pressed = True
            self.update()

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

    def mouseReleaseEvent(self, event) -> None:
        if self._sticker_shadow and self._sticker_pressed:
            self._sticker_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

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
        Sever all reference paths before the button is removed.
        Called by BaseNode._prepare_for_removal via _detach_buttons().
        """
        self._reset_timer.stop()
        self._callback = None


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
        """Sever callback references that capture the parent node."""
        self._get_emoji = None
        self._set_emoji = None
