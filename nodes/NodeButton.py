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
LOD_THRESHOLD   = 0.25      # Below this zoom the buttons disappear


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

        # Keep full-res source pixmaps — scaled once to display size and cached.
        self._pix_normal  = pixmap_normal
        self._pix_confirm = pixmap_confirm
        self._scaled_normal  = None   # cached display-size pixmap
        self._scaled_confirm = None
        self._shadow_cache   = None   # cached shadow pixmap
        self._shadow_source  = None   # tracks which source generated the shadow

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

    def _get_scaled(self, source: QPixmap, size: int) -> QPixmap:
        """Return a display-size cached pixmap, rebuilding only when source changes."""
        if source is self._pix_normal:
            if self._scaled_normal is None:
                self._scaled_normal = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return self._scaled_normal
        else:
            if self._scaled_confirm is None and source is not None:
                self._scaled_confirm = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return self._scaled_confirm

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # LOD gate — hide at low zoom, no overhead below threshold
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod < LOD_THRESHOLD:
            return

        source = (
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

        # Above 0.5 zoom, draw from full-res source for crisp rendering.
        # At 0.5 and below, use cached display-size pixmap for performance.
        if lod > 0.5:
            pix = source
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        else:
            pix = self._get_scaled(source, int(scaled))

        # Tactile press — gentle offset toward bottom-right
        if self._sticker_shadow and self._sticker_pressed:
            draw_rect = draw_rect.translated(self._PRESS_DIST, self._PRESS_DIST)

        # Dynamic radial shadow engine — proof of concept validated, parked until
        # we add literal 3D light source nodes (NullNode as light → directional
        # shadow per button → our own shading engine inside the button framework).
        # Re-enable by wiring a light source position into the shadow direction.

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
        """Return to normal state — called by timer or after execution.

        Defensive: if the parent node's teardown bailed out before detach()
        was called (exception in _prepare_for_removal) the timer can still
        fire. Bail out if our C++ side is gone or the scene is mid bulk
        removal — both are peer-paint-during-burst vectors (see Documents/
        Compliance/Node Cleanup Compliance.md 2026-04-17)."""
        self._reset_timer.stop()
        try:
            sc = self.scene()
        except RuntimeError:
            return
        if sc is None:
            return
        if getattr(sc, '_bulk_removing', 0) > 0:
            return
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
        try:
            self._reset_timer.timeout.disconnect(self._reset)
        except RuntimeError:
            pass
        self._callback = None


EMOJI_OVERFLOW = 4.0  # extra height so emoji glyphs don't clip at the bottom


class EmojiButton(QGraphicsObject):
    """A small button that renders the node's current emoji and shuffles on click.

    The glyph is rendered to a cached QPixmap on first paint or emoji change —
    subsequent paints just blit the pixmap.  At 1200+ nodes × 3 emoji buttons
    each, this avoids 3600+ drawText calls per frame.
    """

    def __init__(self, parent, get_emoji, set_emoji):
        super().__init__(parent)
        self._get_emoji = get_emoji
        self._set_emoji = set_emoji
        self._cached_pixmap = None
        self._cached_emoji  = None
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self._rebuild_cache()   # pre-render at construction, not first paint

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, BUTTON_SIZE, BUTTON_SIZE + EMOJI_OVERFLOW)

    def _rebuild_cache(self) -> None:
        """Render the current emoji glyph to a pixmap for fast blitting."""
        if self._get_emoji is None:
            return
        emoji = self._get_emoji()
        if emoji == self._cached_emoji and self._cached_pixmap is not None:
            return
        self._cached_emoji = emoji
        from PySide6.QtGui import QFont
        size = int(BUTTON_SIZE + EMOJI_OVERFLOW)
        pix = QPixmap(size * 2, size * 2)   # 2x for smooth scaling
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setFont(QFont(Theme.healthFontFamily, int(BUTTON_SIZE * 0.7 * 2)))
        p.setPen(QColor(Theme.nodeFontColor))
        r = pix.rect().adjusted(0, -6, 0, -6)   # nudge glyph up (2x space)
        p.drawText(r, Qt.AlignCenter, emoji)
        p.end()
        self._cached_pixmap = pix.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if self._get_emoji is None:
            return
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod < LOD_THRESHOLD:
            return
        if lod > 0.5:
            # Above 0.5 — render text directly for crisp glyphs
            from PySide6.QtGui import QFont
            painter.setFont(QFont(Theme.healthFontFamily, int(BUTTON_SIZE * 0.7)))
            painter.setPen(QColor(Theme.nodeFontColor))
            r = self.boundingRect().adjusted(0, -3, 0, -3)  # nudge glyph up
            painter.drawText(r, Qt.AlignCenter, self._get_emoji())
        else:
            # Zoomed out — use cached pixmap for performance
            self._rebuild_cache()
            if self._cached_pixmap:
                painter.drawPixmap(0, 0, self._cached_pixmap)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._set_emoji is None:
            event.ignore()
            return
        import random
        from utils.IconPicker import emojiIcons
        self._set_emoji(random.choice(emojiIcons))
        self._cached_pixmap = None   # invalidate cache
        self._cached_emoji  = None
        self.update()
        # Repaint the parent node so the title-row emoji updates too
        if self.parentItem():
            self.parentItem().update()
        event.accept()

    def detach(self) -> None:
        """Sever callback references that capture the parent node."""
        self._cached_pixmap = None
        self._get_emoji = None
        self._set_emoji = None
