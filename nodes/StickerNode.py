#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/StickerNode.py StickerNode class
-Chromeless alpha-PNG sticker — first descendant of ChromelessRoot for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer, QBuffer, QIODevice
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QImage
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QFileDialog

from data.StickerNodeData import StickerNodeData
from nodes.ChromelessRoot import ChromelessRoot
from nodes._shake_detect import arm_cooldown
from pretty_widgets.graphics.Theme import Theme
from shared_braincell.logger import setup_logger

logger = setup_logger("sticker")


class StickerNode(ChromelessRoot):
    """
    Frameless, chromeless PNG sticker. First descendant of ChromelessRoot
    (which carries the viewport-pin + shake-detect + right-click-menu
    machinery all chromeless nodes share). Stands as the reference
    implementation for future raw-image-style nodes (postcards, patches,
    cut-outs) that want the canvas integration without the structural-
    node apparatus.

    No buttons, no border, no caption — just the image with its alpha
    channel composited directly onto the canvas.  Double-click an empty
    sticker to browse for a PNG, double-click a loaded sticker to toggle
    its viewport pin.  Drag to move, corner to resize, shake to delete.

    ── Alpha-channel click-through (a feature, preserve it) ──

    Stickers deliberately have NO opaque background.  `paint()` does not
    fill the rect; it only draws the pixmap.  Everywhere the pixmap's
    alpha channel is transparent, the canvas behind the sticker remains
    visible AND interactable — you can park a sticker on top of a text
    node and still drag-select the text through the transparent regions
    of the image.  The behaviour is pixel-accurate: opaque pixels are
    the sticker, transparent pixels pass through.

    Invariants that must stay intact for this to keep working:

    1. `paint()` must not draw any background fill.  No QBrush, no
       fillRect, no rounded-rect chrome.  Only `paint_content()` runs,
       and `paint_content` only draws the pixmap (plus the empty-state
       placeholder text when there is no image yet).
    2. `_fit_to_image()` sizes the node rect tight to the scaled pixmap
       so there are no captured transparent margins around the image.
    3. The constructor sets `setBrush(Qt.NoBrush)` / `setPen(Qt.NoPen)`
       once at init time.  Now that StickerNode is its own root there is
       no NodeBehaviour trying to paint over it on hover, so the per-call
       `setBrush` override that used to live here is no longer needed.

    ── Node-like contract (duck-typed) ──

    StickerNode is not a BaseNode, but other parts of the app iterate
    scene items looking for `.data`, `.to_dict()`, `.from_dict()`, and
    `.connections`.  All of those are provided here so stickers flow
    through session save, load, selection traversal, and multi-shake
    delete the same way BaseNode variants do.
    """

    _Z_FLOOR      = 100.0   # float above regular nodes, same as ValueNode
    _MIN_WIDTH    = 24.0
    _MIN_HEIGHT   = 24.0
    _RESIZE_GRIP  = 18.0

    def __init__(self, data: StickerNodeData | None = None):
        if data is None:
            data = StickerNodeData()
        # Root handles: pos, z, flags, pin state, shake detector,
        # _removal_done, connections list, pin-restore timer.
        super().__init__(data)

        # Sticker-specific state the root doesn't know about.
        self._pending_shake_delete = False
        self._is_resizing       = False
        self._resize_start_pos  = QPointF()
        self._resize_start_rect = QRectF()
        self._pixmap: QPixmap | None = None

        # Alpha-click-through requires no fill / no border + no Qt caching
        # so every repaint reads the current alpha channel honestly.
        self.setBrush(Qt.NoBrush)
        self.setPen(Qt.NoPen)
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

        # Apply StickerNode's z-floor — setZValue is overridden to enforce
        # the floor on every subsequent setZValue call too.
        self.setZValue(max(data.z_value, self._Z_FLOOR))

        # Load image with cache-first hierarchy:
        #   1. cache_key → load from the content-addressed cache, run drift
        #      check against source_path if present
        #   2. source_path → cache the raw bytes, then load from the cached
        #      file (so a second run with no cache_key upgrades the state)
        #   3. image_b64 → legacy pre-cache session, migrate into the cache
        #      on next save via _encode_b64 → cache_pixmap
        if data.cache_key:
            self._load_from_cache_with_drift_check()
        elif data.source_path:
            self._load_from_path(data.source_path)
        elif data.image_b64:
            self._load_from_b64(data.image_b64)

    # ── Z depth ──────────────────────────────────────────────────────────────

    def setZValue(self, z: float) -> None:
        super().setZValue(max(z, self._Z_FLOOR))

    # ── Image loading (cache-integrated) ────────────────────────────────────

    def _load_from_path(self, path: str) -> None:
        """Load from disk AND cache the raw bytes in a single read.
        Updates cache_key, source_path, source_size, source_mtime so the
        next session restore takes the fast cache-first path.
        The cached file is the same bytes as the source — format and
        metadata (EXIF, XMP, ICC, tEXt stamps) are preserved verbatim."""
        from utils.persistence.media_cache import cache_source_bytes
        p = Path(path)
        if not p.exists():
            return
        try:
            raw = p.read_bytes()
        except OSError:
            return
        if not raw:
            return
        try:
            self.data.cache_key = cache_source_bytes(raw, p.suffix)
        except Exception:
            pass
        img = QImage()
        img.loadFromData(raw)
        if not img.isNull():
            self._pixmap = QPixmap.fromImage(img)
            self.data.source_path = str(p.resolve())
            try:
                st = p.stat()
                self.data.source_size  = st.st_size
                self.data.source_mtime = st.st_mtime
            except OSError:
                pass
            self._fit_to_image()
        self.update()

    def _load_from_cache_with_drift_check(self) -> None:
        """Primary load path — pull the pixmap from the content-addressed
        cache, then verify the source file on disk hasn't drifted away
        from the cached bytes.  Fingerprint (size + mtime) short-circuits
        the full SHA when nothing's moved; a hash mismatch queues an
        AboutNode warning next to the sticker.  Policy is flag-don't-
        auto-fix — the user decides whether the drift is a drift."""
        from utils.persistence.media_cache import load_cached, hash_file, key_hash
        pixmap = load_cached(self.data.cache_key)
        if pixmap is None or pixmap.isNull():
            # Cache miss — fall back to source, which also re-caches.
            if self.data.source_path:
                self._load_from_path(self.data.source_path)
            return
        self._pixmap = pixmap
        self._fit_to_image()
        self.update()

        if not self.data.source_path:
            return
        sp = Path(self.data.source_path)
        if not sp.exists():
            return
        try:
            st = sp.stat()
            cur_size, cur_mtime = st.st_size, st.st_mtime
        except OSError:
            cur_size, cur_mtime = 0, 0.0
        fingerprint_clean = (
            cur_size == self.data.source_size
            and abs(cur_mtime - self.data.source_mtime) < 1.0
            and self.data.source_size != 0
        )
        if fingerprint_clean:
            return
        src_hash = hash_file(sp)
        if src_hash and src_hash != key_hash(self.data.cache_key):
            self._queue_drift_notification(sp.name)
        # Record the fingerprint we just observed so the next restore sees
        # a clean match and stays silent — we've already surfaced this state.
        self.data.source_size  = cur_size
        self.data.source_mtime = cur_mtime

    def _queue_drift_notification(self, filename: str) -> None:
        """Spawn an AboutNode near the sticker announcing the drift.
        Deferred so the scene is fully constructed before we add items."""
        msg = f"sticker source drifted — cache no longer matches\n{filename}"
        def _spawn():
            scene = self.scene()
            if not scene or not hasattr(scene, 'add_about_node'):
                return
            pos = self.mapToScene(self.rect().topRight()) + QPointF(40, -10)
            try:
                scene.add_about_node(pos=pos, message=msg)
            except TypeError:
                # Older add_about_node signatures may not accept `message`;
                # fall back to the safer no-message call and swallow the miss.
                try:
                    scene.add_about_node(pos=pos)
                except Exception:
                    pass
        QTimer.singleShot(250, _spawn)

    def _load_from_b64(self, b64: str) -> None:
        """Legacy path — base64-encoded PNG from a pre-cache session.
        On next save the pixmap will be migrated into the cache via
        `to_dict` → `cache_pixmap`, and the b64 field stops being written."""
        raw = base64.b64decode(b64)
        img = QImage()
        img.loadFromData(raw)
        if not img.isNull():
            self._pixmap = QPixmap.fromImage(img)
            self._fit_to_image()
        self.update()

    def _fit_to_image(self) -> None:
        """Set node size to match the scaled image — tight, no margins.
        Only acts while the rect is still at the 200×200 default so that
        user-resized stickers are not clobbered by a later image load."""
        if self._pixmap and not self._pixmap.isNull():
            if self.data.width == 200.0 and self.data.height == 200.0:
                pw, ph = self._pixmap.width(), self._pixmap.height()
                scale = min(400.0 / max(pw, 1), 400.0 / max(ph, 1), 1.0)
                self.data.width  = pw * scale
                self.data.height = ph * scale
                self.prepareGeometryChange()
                self.setRect(QRectF(0, 0, self.data.width, self.data.height))

    def _encode_b64(self) -> str:
        """Encode the current pixmap as base64 PNG for session persistence."""
        if not self._pixmap or self._pixmap.isNull():
            return ""
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self._pixmap.save(buf, "PNG")
        return base64.b64encode(buf.data().data()).decode("ascii")

    # ── Interaction ──────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._pixmap and not self._pixmap.isNull():
            # Has an image — double-click toggles the viewport pin
            self._toggle_pin()
        else:
            # Empty sticker — double-click browses for a PNG
            path, _ = QFileDialog.getOpenFileName(
                None, "Choose Sticker Image", "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)"
            )
            if path:
                self._load_from_path(path)
        event.accept()

    def mousePressEvent(self, event):
        # Right-click → root handles the pin context menu via its own
        # mousePressEvent path. Defer cleanly so _extra_context_menu_items
        # gets its chance for sticker-only entries (currently none).
        if event.button() == Qt.RightButton:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            # Corner resize-grip hit test — sticker-specific bespoke
            # gesture, claim the event before super() arms shake-detect.
            rect = self.rect()
            handle = QRectF(rect.right()  - self._RESIZE_GRIP,
                            rect.bottom() - self._RESIZE_GRIP,
                            self._RESIZE_GRIP, self._RESIZE_GRIP)
            if handle.contains(event.pos()):
                self._is_resizing       = True
                self._resize_start_pos  = event.pos()
                self._resize_start_rect = self.rect()
                # Symmetry with mouseReleaseEvent's super() call — the
                # release path always calls super (which increments
                # ChromelessRoot's _release_seq counter), so the press
                # path must too or every sticker resize produces a
                # false-positive ORPHAN release warning. Same pattern as
                # BaseNode's 2026-05-02 resize-path symmetry fix.
                # ChromelessRoot's mousePressEvent runs its drag-gate ARM
                # (sets _drag_press_screen_pos etc.), but StickerNode's
                # mouseMoveEvent intercepts on _is_resizing before super
                # so the gate never actually runs during a resize.
                super().mousePressEvent(event)
                event.accept()
                return
            # Hide the cursor while dragging — the sticker should look
            # like it's peeling from the fingertip, not chasing an arrow.
            view = self._get_view()
            if view:
                view.setCursor(Qt.BlankCursor)
        # Defer shake-arm and drag plumbing to the root.
        super().mousePressEvent(event)

    def _extra_context_menu_items(self, ctx) -> None:
        """StickerNode has no extra context-menu entries right now —
        pin is the only action. Hook is declared so future additions
        (reload image, re-centre, etc.) land here."""
        pass

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            delta      = event.pos() - self._resize_start_pos
            new_width  = max(self._MIN_WIDTH,  self._resize_start_rect.width()  + delta.x())
            new_height = max(self._MIN_HEIGHT, self._resize_start_rect.height() + delta.y())
            if event.modifiers() & Qt.ShiftModifier:
                ratio = self._resize_start_rect.width() / self._resize_start_rect.height()
                new_height = new_width / ratio
            self.prepareGeometryChange()
            self.setRect(QRectF(self.rect().topLeft(), QSizeF(new_width, new_height)))
            self.update()
            event.accept()
            return
        # Root handles super() + shake tracking.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        # Root syncs geometry + calls shake.release().
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            view = self._get_view()
            if view:
                view.unsetCursor()
        # Release any lingering scene grab on this item.
        if not event.buttons():
            scene = self.scene()
            if scene and scene.mouseGrabberItem() is self:
                self.ungrabMouse()
        # Deferred shake-delete — pre-clear dispatch state NOW, then
        # schedule the actual removeItem for the next event-loop tick.
        # Capture the scene rect before deferring so we can invalidate
        # it after the removeItem fires (prevents the ghost-linger seen
        # on 2026-04-18 when heavy particle load starves the paint loop).
        if self._pending_shake_delete:
            self._pending_shake_delete = False
            scene = self.scene()
            if scene:
                self.setSelected(False)
                self.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
                try:
                    ghost_rect = self.mapRectToScene(self.boundingRect())
                except RuntimeError:
                    ghost_rect = None
                def _deferred_remove(node=self, sc=scene, r=ghost_rect):
                    try:
                        if sc.mouseGrabberItem() is node:
                            node.ungrabMouse()
                    except RuntimeError:
                        pass
                    try:
                        sc.removeItem(node)
                    except RuntimeError:
                        pass
                    if r is not None:
                        try:
                            sc.invalidate(r)
                        except RuntimeError:
                            pass
                QTimer.singleShot(0, _deferred_remove)

    def _on_shake_triggered(self) -> None:
        """ShakeDetector fires this once per accepted shake gesture.
        Kicks off the particle burst and marks the sticker for deferred
        removal on mouseRelease."""
        scene = self.scene()
        if not scene:
            return
        # Snapshot the sticker's data so the sidebar can restore it.
        try:
            scene._last_deleted = self.to_dict()
        except Exception:
            pass
        arm_cooldown()
        # Pre-shake quieting — sever pin signals synchronously before the
        # deferred-removeItem window opens.
        try:
            self._quiet_for_shake()
        except Exception:
            pass
        # Particles.  Import deferred — Particles module itself imports
        # from graphics.Scene which may not have finished loading at the
        # time StickerNode is imported during session restore.
        from graphics.Particles import sprinkle, orbital_burst, shake_mode
        center = self.mapToScene(self.rect().center())
        if shake_mode == "orbital":
            orbital_burst(scene, center)
        else:
            sprinkle(scene, center, count=8000)
        self._pending_shake_delete = True

    # ── Paint ────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        """Skip all chrome — just the image.
        Do NOT add any background fill here: the transparent regions are
        load-bearing for the alpha-channel click-through feature
        (see class docstring)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.paint_content(painter)
        painter.restore()

    def paint_content(self, painter: QPainter) -> None:
        if not self._pixmap or self._pixmap.isNull():
            # Empty-state placeholder — the one bit of text a sticker ever shows
            painter.setPen(Theme.textPrimary)
            painter.drawText(self.rect(), Qt.AlignCenter, "double-click\nto load sticker")
            return

        r = self.rect()
        scaled = self._pixmap.size().scaled(r.size().toSize(), Qt.KeepAspectRatio)
        x = r.x() + (r.width()  - scaled.width())  / 2
        y = r.y() + (r.height() - scaled.height()) / 2
        dest = QRectF(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(dest.toRect(), self._pixmap)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    def boundingRect(self):
        return self.rect()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    # itemChange — ChromelessRoot handles scene-leave via the demolition
    # crew. Root also holds _removal_done + the _on_viewport_changed
    # race guard that used to live here.

    # _quiet_for_shake — inherited from ChromelessRoot. Default body
    # disconnects viewport tracking, which is exactly what we need.
    # The 2026-04-18 0xc0000409 fix that originated here has been lifted
    # to the root so the entire chromeless family gets it for free.

    def _demolition_pre(self) -> None:
        """Sever viewport tracking (via super) and release the pixmap
        buffer before the crew runs its standard sequence."""
        super()._demolition_pre()
        self._pixmap = None

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        # Cache-first persistence: if the pixmap has no cache_key yet,
        # push it into the cache now so the session JSON only carries the
        # hash key, not a base64 blob.  Covers pasted/generated stickers
        # that never had a source file on disk.
        if self._pixmap and not self.data.cache_key:
            from utils.persistence.media_cache import cache_pixmap
            try:
                self.data.cache_key = cache_pixmap(self._pixmap)
            except Exception:
                pass
        # True legacy tail: only fall back to b64 if we have neither a
        # cache_key nor a source_path.  In practice this branch should
        # never fire for new stickers — it exists purely to keep
        # pre-cache sessions survivable.
        if (not self.data.source_path
                and not self.data.cache_key
                and self._pixmap):
            self.data.image_b64 = self._encode_b64()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'StickerNode':
        return StickerNode(StickerNodeData.from_dict(data))
