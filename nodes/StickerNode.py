#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/StickerNode.py StickerNode root type
-A first-class root of its own, no BaseNode inheritance, just image and canvas
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer, QBuffer, QIODevice
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QImage
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QFileDialog

from data.StickerNodeData import StickerNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger
from nodes._shake_detect import ShakeDetector, arm_cooldown

logger = setup_logger("sticker")


class StickerNode(QGraphicsRectItem):
    """
    Frameless, chromeless PNG sticker.  First-class root type — does NOT
    inherit from BaseNode.  Stands as the reference implementation for
    future raw-image-style nodes (postcards, patches, cut-outs) that want
    the canvas integration without the structural-node apparatus.

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
        super().__init__(QRectF(0, 0, data.width, data.height))
        self.setPos(data.x, data.y)

        self.data = data
        # `connections` stays empty for the lifetime of a sticker — they
        # have no ports — but the attribute must exist because graphics/
        # Connection.py and the scene's chain-select walkers duck-type on
        # it.  An empty list is the safest possible presence.
        self.connections: list = []

        # Teardown guards (shared contract with BaseNode variants)
        self._removal_done = False
        self._pending_shake_delete = False

        # Resize-at-corner state
        self._is_resizing       = False
        self._resize_start_pos  = QPointF()
        self._resize_start_rect = QRectF()

        # Composed shake detector — stickers use the same physical feel
        # and shared cooldown as every other shake-delete in the app.
        self._shake = ShakeDetector(on_shake=self._on_shake_triggered)

        # Image + pin state
        self._pixmap: QPixmap | None = None
        self._pin_connected = False

        # Qt flags — movable + selectable by default, disabled only while
        # pinned.  ItemSendsScenePositionChanges so itemChange sees moves.
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

        # No border, no fill — load-bearing for the alpha click-through.
        self.setBrush(Qt.NoBrush)
        self.setPen(Qt.NoPen)
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
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

        # Pinned stickers track the viewport — re-establish the pin once
        # the scene / view are fully constructed.
        if data.pinned:
            QTimer.singleShot(0, self._activate_pin)

    # ── Node-like contract ───────────────────────────────────────────────────

    def sync_data(self) -> None:
        """Fold current geometry back into the dataclass."""
        self.data.x = self.pos().x()
        self.data.y = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        self.data.z_value = self.zValue()

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
        from utils.media_cache import cache_source_bytes
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
        from utils.media_cache import load_cached, hash_file, key_hash
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
        if event.button() == Qt.RightButton:
            self._show_context_menu(event)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # Corner resize-grip hit test
            rect = self.rect()
            handle = QRectF(rect.right()  - self._RESIZE_GRIP,
                            rect.bottom() - self._RESIZE_GRIP,
                            self._RESIZE_GRIP, self._RESIZE_GRIP)
            if handle.contains(event.pos()):
                self._is_resizing       = True
                self._resize_start_pos  = event.pos()
                self._resize_start_rect = self.rect()
                event.accept()
                return
            # Hide the cursor while dragging — the sticker should look
            # like it's peeling from the fingertip, not chasing an arrow.
            view = self._get_view()
            if view:
                view.setCursor(Qt.BlankCursor)
            # Arm the shake detector for the duration of this drag.
            self._shake.press()
        super().mousePressEvent(event)

    def _show_context_menu(self, event) -> None:
        """Right-click menu. Pin toggle is the primary action — discoverable,
        checkable, matches the Intricate voice (PrettyMenu chrome)."""
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
        super().mouseMoveEvent(event)
        # Feed the shake detector with the post-move scene position + the
        # view's current zoom so shake threshold is zoom-independent.
        zoom = 1.0
        scene = self.scene()
        if scene and scene.views():
            zoom = getattr(scene.views()[0], 'current_zoom', 1.0)
        self._shake.track(self.scenePos(), zoom)

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        self._shake.release()
        # Sync geometry back to the dataclass now that the gesture ended.
        self.data.x = self.pos().x()
        self.data.y = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
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

    # ── Viewport pinning ─────────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        if self.data.pinned:
            self._deactivate_pin()
        else:
            self._activate_pin()

    def _activate_pin(self) -> None:
        """Pin the sticker to its current viewport position."""
        self.data.pinned = True
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        view = self._get_view()
        if view:
            vp_pos = view.mapFromScene(self.pos())
            self.data.pin_vp_x = vp_pos.x()
            self.data.pin_vp_y = vp_pos.y()
            self._connect_viewport_tracking(view)

    def _deactivate_pin(self) -> None:
        """Unpin — sticker becomes draggable again and moves with the canvas."""
        self.data.pinned = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._disconnect_viewport_tracking()

    def _connect_viewport_tracking(self, view) -> None:
        if self._pin_connected:
            return
        # Primary channel: the view declares its transform changes directly.
        # Pan-by-translate and wheel-zoom both mutate the transform without
        # moving the scrollbars, so this is the signal that actually fires
        # during normal canvas navigation.
        if hasattr(view, 'viewTransformed'):
            view.viewTransformed.connect(self._on_viewport_changed)
        # Secondary channel: scrollbars. Only ever move when the scene rect
        # grows past the viewport — rare, but free to keep wired as backup.
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
        """Canvas transform moved — remap the sticker back to its recorded
        viewport coordinate so it stays anchored in screen space."""
        # Signal-destructor race guard.  A transform tick firing into a
        # sticker mid-teardown tripped 0xc0000409 (Qt fastfail) on
        # 2026-04-18; leave these checks in place.
        import shiboken6
        if not shiboken6.isValid(self):
            return
        scene = self.scene()
        if scene is None or getattr(scene, '_bulk_removing', 0) > 0:
            return
        if self._removal_done:
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

    def itemChange(self, change, value):
        if (change == QGraphicsRectItem.GraphicsItemChange.ItemSceneChange
                and value is None and not self._removal_done):
            logger.log(5, "[REMOVE] sticker %s leaving scene — _prepare_for_removal starting",
                        self.data.uuid[:8])
            self._prepare_for_removal()
            logger.log(5, "[REMOVE] sticker %s _prepare_for_removal complete",
                        self.data.uuid[:8])
        return super().itemChange(change, value)

    def _quiet_for_shake(self) -> None:
        """Synchronously silence viewport tracking before the deferred-
        removeItem window opens.  Without this, a viewTransformed or
        scrollbar tick landing between shake-start and removeItem can
        collide with the destructor and fastfail the process (0xc0000409,
        2026-04-18)."""
        self._disconnect_viewport_tracking()

    def _prepare_for_removal(self) -> None:
        """Idempotent teardown hook.  Same contract as BaseNode's version
        but without the connection / ports / behaviour plumbing."""
        if self._removal_done:
            return
        self._removal_done = True
        # Invalidate the scene region so ghost pixels clear promptly after
        # removeItem (matches the BaseNode phase 0 pattern).
        scene = self.scene()
        if scene:
            try:
                scene.invalidate(self.mapRectToScene(self.boundingRect()))
            except RuntimeError:
                pass
        self._disconnect_viewport_tracking()
        self._pixmap = None

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        # Cache-first persistence: if the pixmap has no cache_key yet,
        # push it into the cache now so the session JSON only carries the
        # hash key, not a base64 blob.  Covers pasted/generated stickers
        # that never had a source file on disk.
        if self._pixmap and not self.data.cache_key:
            from utils.media_cache import cache_pixmap
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
