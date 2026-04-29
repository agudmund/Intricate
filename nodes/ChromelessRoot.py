#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/ChromelessRoot.py ChromelessRoot base class
-Common ancestor for the chromeless family — pin, shake, context menu for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import traceback

from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem

from data.ChromelessRootData import ChromelessRootData
from nodes._shake_detect import ShakeDetector, arm_cooldown
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger, TRACE

logger = setup_logger("chromeless")

# ─────────────────────────────────────────────────────────────────────────────
# FORENSIC LOGGING — 2026-04-22 JoyStatsNode cross-node-destruction incident
# ─────────────────────────────────────────────────────────────────────────────
# User reported: clicking a JoyStatsNode occasionally triggers the demolition
# crew AND takes a neighbouring StickerNode with it. Not replicable on demand.
# Every interesting codepath in the chromeless family now emits a log line so
# the next occurrence leaves a full paper trail. When the bug is caught and
# closed, these logs can be demoted to DEBUG or stripped.
# ─────────────────────────────────────────────────────────────────────────────

# Map Qt's GraphicsItemChange enum to readable names for logging.
_ITEM_CHANGE_NAMES = {
    getattr(QGraphicsItem, name, None): name for name in (
        'ItemPositionChange', 'ItemPositionHasChanged',
        'ItemSceneChange', 'ItemSceneHasChanged',
        'ItemMatrixChange', 'ItemTransformChange', 'ItemTransformHasChanged',
        'ItemSelectedChange', 'ItemSelectedHasChanged',
        'ItemVisibleChange', 'ItemVisibleHasChanged',
        'ItemEnabledChange', 'ItemEnabledHasChanged',
        'ItemChildAddedChange', 'ItemChildRemovedChange',
        'ItemParentChange', 'ItemParentHasChanged',
        'ItemFlagsChange', 'ItemFlagsHaveChanged',
        'ItemZValueChange', 'ItemZValueHasChanged',
        'ItemOpacityChange', 'ItemOpacityHasChanged',
        'ItemCursorChange', 'ItemCursorHasChanged',
        'ItemToolTipChange', 'ItemToolTipHasChanged',
        'ItemRotationChange', 'ItemRotationHasChanged',
        'ItemScaleChange', 'ItemScaleHasChanged',
        'ItemTransformOriginPointChange', 'ItemTransformOriginPointHasChanged',
        'ItemScenePositionHasChanged',
    ) if hasattr(QGraphicsItem, name)
}


class ChromelessRoot(QGraphicsRectItem):
    """Base class for the chromeless family of nodes.

    Sibling to BaseNode rather than descendant — inherits
    ``QGraphicsRectItem`` directly. Carries the mechanics every
    chromeless node needs (viewport pin, shake-delete, right-click
    context menu, teardown hook) without any of BaseNode's chrome
    apparatus (title row, button strip, emoji accent, hover pulse).

    First three concrete descendants: StickerNode (Phase 1),
    JoyStatsNode (Phase 2), ValueNode (Phase 3). Future raw-node
    siblings (postcards, patches, cut-outs, chromeless HUDs) inherit
    here too.

    Subclass contract:

    * Construct a ``ChromelessRootData`` subclass and pass it to
      ``super().__init__(data)``. The dataclass brings the three pin
      fields ``pinned``, ``pin_vp_x``, ``pin_vp_y`` for free.
    * Override ``paint()`` to render the node. The root does NOT paint
      anything — every chromeless node owns its full visual.
    * Optionally override ``_extra_context_menu_items(ctx)`` to add
      menu entries beyond the built-in pin toggle. The hook is called
      after the pin toggle is inserted, so subclass items appear below
      it in the menu.
    * If type-specific teardown is needed, override ``_demolition_pre``
      and call ``super()._demolition_pre()`` to preserve the pin-tracking
      disconnect. Otherwise the root handles it automatically via
      ``itemChange`` on scene-leave.

    Deliberately NOT provided at this level (type-specific concerns
    that belong in subclasses):

    * Alpha-aware ``shape()`` / ``boundingRect()`` — StickerNode-only;
      other chromeless nodes are opaque rectangular.
    * Image cache, drift detection, fit-to-image — StickerNode-only.
    * Ports — ValueNode-only for now; add per-subclass when needed.
    * Body paint, title paint, background fill — every subclass
      renders what it needs.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # CLASS FLAGS — subclasses override to opt into generic behaviours
    # ─────────────────────────────────────────────────────────────────────────

    # When True, the root offers a bottom-right corner-grip resize while
    # unpinned — drag the grip to set the node's fixed size. The size
    # the user lands on becomes the frozen screen-space size on the next
    # pin. StickerNode stays False (it has its own bespoke resize with
    # aspect-ratio preservation + cursor-hide); JoyStatsNode and ValueNode
    # opt in to get the generic grip for free.
    _UNPINNED_RESIZE_ENABLED = False
    _RESIZE_GRIP_SIZE        = 18.0
    _RESIZE_MIN_WIDTH        = 40.0
    _RESIZE_MIN_HEIGHT       = 40.0

    # ─────────────────────────────────────────────────────────────────────────
    # CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self, data: ChromelessRootData):
        super().__init__(0, 0, data.width, data.height)
        self.data = data
        self.setPos(data.x, data.y)
        self.setZValue(data.z_value)

        # `connections` stays empty for the lifetime of a chromeless
        # node by default — most of them have no ports. The attribute
        # must exist because graphics/Connection.py and the scene's
        # chain-select walkers duck-type on it. Subclasses with real
        # ports (ValueNode) manage this list themselves.
        self.connections: list = []

        # Teardown guards — matches the StickerNode contract shared with
        # the demolition crew.
        self._removal_done = False

        # Shake-delete detector — composition, not inheritance. Every
        # chromeless node participates in the shake gesture by default;
        # subclasses can override _on_shake_triggered to customise the
        # removal (e.g., StickerNode's orbital burst variant).
        self._shake = ShakeDetector(on_shake=self._on_shake_triggered)
        self._shake_triggered = False

        # Pin state
        self._pin_connected = False

        # Generic unpinned resize state — used only when the subclass opts
        # in via ``_UNPINNED_RESIZE_ENABLED``. Start empty; mousePressEvent
        # populates these on a corner-grip hit.
        self._chrome_resizing       = False
        self._chrome_resize_start   = QPointF()
        self._chrome_resize_rect0   = QRectF()

        # Default interaction flags. Pin toggle disables ItemIsMovable
        # while pinned; ItemSendsScenePositionChanges so itemChange gets
        # move/leave events.
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

        logger.log(TRACE, "[chrome-init] %s CONSTRUCTED pos=(%.1f,%.1f) size=(%.1f,%.1f) pinned=%s z=%.1f",
                   self._log_id(), data.x, data.y, data.width, data.height,
                   data.pinned, data.z_value)

        # Restore pin state if the data says so — deferred one tick so
        # scene/view are fully constructed by the time we ask. Critical:
        # pass from_saved_vp=True so the saved pin_vp coords are HONOURED
        # rather than overwritten from the current (possibly pre-camera-
        # restore) view transform. See _activate_pin for the rationale.
        if data.pinned:
            logger.info("[chrome-init] %s scheduling pin restore (saved vp=%.1f,%.1f)",
                        self._log_id(), data.pin_vp_x, data.pin_vp_y)
            QTimer.singleShot(0, lambda: self._activate_pin(from_saved_vp=True))

    # ─────────────────────────────────────────────────────────────────────────
    # LOGGING IDENTITY
    # ─────────────────────────────────────────────────────────────────────────

    def _log_id(self) -> str:
        """Short identifier for every log line — type + short uuid + title.
        Stable across the node's lifetime; readable at a glance in the trail."""
        try:
            short_uuid = getattr(self.data, 'uuid', 'no-uuid')[:8]
            title = getattr(self.data, 'title', '?')
            return f"{type(self).__name__}[{short_uuid}:{title!r}]"
        except Exception:
            return f"{type(self).__name__}[??]"

    # ─────────────────────────────────────────────────────────────────────────
    # NODE-LIKE CONTRACT (matches BaseNode / StickerNode enough to be interchangeable)
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        """Fold current geometry back into the dataclass — called on
        mouse-release and before serialisation."""
        logger.log(TRACE, "[chrome-sync] %s sync_data pos=(%.1f,%.1f) size=(%.1f,%.1f)",
                     self._log_id(), self.pos().x(), self.pos().y(),
                     self.rect().width(), self.rect().height())
        self.data.x = self.pos().x()
        self.data.y = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        self.data.z_value = self.zValue()

    # ─────────────────────────────────────────────────────────────────────────
    # MOUSE HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        btn = ("right" if event.button() == Qt.RightButton
               else "left" if event.button() == Qt.LeftButton else "other")
        logger.log(TRACE, "[chrome-mouse] %s PRESS button=%s pos=(%.1f,%.1f)",
                   self._log_id(), btn, event.pos().x(), event.pos().y())
        if event.button() == Qt.RightButton:
            logger.log(TRACE, "[chrome-mouse] %s → context menu", self._log_id())
            self._show_context_menu(event)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # Generic unpinned corner-grip resize — bottom-right handle,
            # only active when the subclass opted in and the node is
            # currently unpinned. Resizing while unpinned is how the user
            # tells us "freeze THIS size on the next pin". Claim the event
            # before shake-arm so a resize-drag isn't mistaken for shake.
            if (self._UNPINNED_RESIZE_ENABLED
                    and not self.data.pinned
                    and self._hit_resize_grip(event.pos())):
                logger.log(TRACE, "[chrome-mouse] %s → resize grip hit", self._log_id())
                self._chrome_resizing     = True
                self._chrome_resize_start = event.pos()
                self._chrome_resize_rect0 = self.rect()
                event.accept()
                return
            # Arm the shake detector for the duration of this drag.
            logger.log(TRACE, "[chrome-mouse] %s → shake.press()", self._log_id())
            self._shake.press()
        super().mousePressEvent(event)
        logger.log(TRACE, "[chrome-mouse] %s PRESS returned (super called)", self._log_id())

    def _hit_resize_grip(self, local_pos: QPointF) -> bool:
        """Bottom-right ``_RESIZE_GRIP_SIZE`` square of the node rect.
        Item-local coords — matches the coordinate space that ``event.pos()``
        arrives in (which is scene-units when unpinned, the only state
        the grip is active in)."""
        rect = self.rect()
        grip = QRectF(rect.right()  - self._RESIZE_GRIP_SIZE,
                      rect.bottom() - self._RESIZE_GRIP_SIZE,
                      self._RESIZE_GRIP_SIZE, self._RESIZE_GRIP_SIZE)
        return grip.contains(local_pos)

    def mouseMoveEvent(self, event):
        # Generic resize path — consume the drag, update the rect, don't
        # hand it to super() (super would otherwise translate the node).
        if self._chrome_resizing:
            delta = event.pos() - self._chrome_resize_start
            new_w = max(self._RESIZE_MIN_WIDTH,
                        self._chrome_resize_rect0.width()  + delta.x())
            new_h = max(self._RESIZE_MIN_HEIGHT,
                        self._chrome_resize_rect0.height() + delta.y())
            self.prepareGeometryChange()
            self.setRect(QRectF(self.rect().topLeft(), QSizeF(new_w, new_h)))
            self.update()
            event.accept()
            return
        logger.log(TRACE, "[chrome-mouse] %s MOVE scene_pos=(%.1f,%.1f)",
                     self._log_id(), self.scenePos().x(), self.scenePos().y())
        super().mouseMoveEvent(event)
        zoom = 1.0
        scene = self.scene()
        if scene and scene.views():
            zoom = getattr(scene.views()[0], 'current_zoom', 1.0)
        self._shake.track(self.scenePos(), zoom)

    def mouseReleaseEvent(self, event):
        btn = ("right" if event.button() == Qt.RightButton
               else "left" if event.button() == Qt.LeftButton else "other")
        logger.log(TRACE, "[chrome-mouse] %s RELEASE button=%s shake_triggered=%s removal_done=%s",
                   self._log_id(), btn, self._shake_triggered, self._removal_done)
        # Always clear the resize flag — a release ends whatever gesture
        # was in progress. sync_data() below captures the final rect
        # into the dataclass so the frozen-size invariant persists.
        self._chrome_resizing = False
        self._shake.release()
        self.sync_data()
        super().mouseReleaseEvent(event)
        logger.log(TRACE, "[chrome-mouse] %s RELEASE returned (super called)", self._log_id())

    # ─────────────────────────────────────────────────────────────────────────
    # CONTEXT MENU
    # ─────────────────────────────────────────────────────────────────────────

    def _show_context_menu(self, event) -> None:
        """Right-click menu. The pin toggle is built in at the root;
        subclasses add their own entries via ``_extra_context_menu_items``."""
        logger.log(TRACE, "[chrome-ctx] %s showing context menu (pinned=%s)",
                   self._log_id(), self.data.pinned)
        from pretty_widgets.PrettyMenu import menu as pretty_menu
        ctx = pretty_menu()
        pin_action = ctx.addAction("Pin to Viewport")
        pin_action.setCheckable(True)
        pin_action.setChecked(self.data.pinned)
        pin_action.triggered.connect(self._toggle_pin)
        # Subclass hook — runs after the pin toggle is inserted, so
        # subclass entries appear below it.
        self._extra_context_menu_items(ctx)
        # Map scene-space event position to screen for the menu.
        view = self._get_view()
        if view:
            screen_pos = view.mapToGlobal(view.mapFromScene(event.scenePos()))
        else:
            screen_pos = event.screenPos()
        ctx.exec(screen_pos)
        logger.log(TRACE, "[chrome-ctx] %s context menu closed", self._log_id())

    def _extra_context_menu_items(self, ctx) -> None:
        """Override hook — subclasses extend the right-click menu.

        Called after the pin toggle is inserted, so subclass entries
        appear below it. Default: no additions.

        Typical usage in a subclass::

            def _extra_context_menu_items(self, ctx):
                reload_action = ctx.addAction("Reload image")
                reload_action.triggered.connect(self._reload)
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # VIEWPORT PINNING
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        logger.log(TRACE, "[chrome-pin] %s TOGGLE (current=%s)", self._log_id(), self.data.pinned)
        if self.data.pinned:
            self._deactivate_pin()
        else:
            self._activate_pin()

    def _activate_pin(self, from_saved_vp: bool = False) -> None:
        """Pin to a viewport position — two callers with different needs:

        User-initiated (``from_saved_vp=False``): the node sits at some
        on-screen position the user wants to freeze. Compute pin_vp
        from the current scene pos through the current view transform
        and store it.

        Session restore (``from_saved_vp=True``): the data already
        carries valid pin_vp coords from when the session was saved.
        DO NOT overwrite them — the view transform at restore time may
        not yet be the saved camera (camera restore is also QTimer-
        deferred), so mapFromScene(self.pos()) would produce garbage
        pin_vp values. Instead, connect tracking and immediately apply
        the saved pin_vp to the scene pos so the node lands where it
        was pinned regardless of viewTransformed timing.

        2026-04-22 bug: restore path was always overwriting pin_vp on
        load, causing pinned stickers to vanish off-screen after an
        app restart. Fixed by the two-path split.

        ``ItemIgnoresTransformations`` is also toggled on here — while
        pinned, the node renders at fixed screen-space scale regardless
        of canvas zoom. The scene position is still anchored via the
        view transform's translation (``mapToScene(pin_vp)`` in
        ``_on_viewport_changed``), but the zoom factor is stripped from
        the item's own rendering. Unpinning flips the flag back off so
        the item scales with the canvas again (and becomes resizable
        via the subclass's resize gesture). The node's rect() size is
        thus "what you set while unpinned = the frozen screen size".
        """
        logger.log(TRACE, "[chrome-pin] %s ACTIVATE from_saved_vp=%s", self._log_id(), from_saved_vp)
        self.data.pinned = True
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        view = self._get_view()
        if view is None:
            logger.warning("[chrome-pin] %s ACTIVATE called but no view available",
                           self._log_id())
            # Still set IIT so a later view appearance renders consistently.
            self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            return
        if not from_saved_vp:
            # User-initiated pin. The rect currently lives in scene-unit
            # space (IIT off). IIT on reads rect as screen-pixel space,
            # so multiply by the current zoom to keep the *visible* size
            # continuous across the toggle. Without this, re-pinning at
            # any zoom != 1x snaps visible size by the zoom factor —
            # the "snap back on re-pin" bug the user reported.
            zoom = float(getattr(view, 'current_zoom', 1.0)) or 1.0
            if zoom != 1.0:
                cur = self.rect()
                self.prepareGeometryChange()
                self.setRect(QRectF(cur.topLeft(),
                                    QSizeF(cur.width()  * zoom,
                                           cur.height() * zoom)))
                logger.log(TRACE, "[chrome-pin] %s ACTIVATE rescaled rect ×%.3f (zoom) → (%.1f,%.1f)",
                           self._log_id(), zoom, self.rect().width(), self.rect().height())
            # Capture pin_scale so paint_content can compensate hardcoded
            # font sizes (which IIT renders at full pt regardless of zoom).
            # Without this, pinning at zoom != 1 visibly grows or shrinks
            # text relative to the rect — see ChromelessRootData.pin_scale.
            self.data.pin_scale = zoom
            # Anchor to the current on-screen position. mapFromScene
            # reports viewport-pixel coords regardless of IIT state.
            vp_pos = view.mapFromScene(self.pos())
            self.data.pin_vp_x = vp_pos.x()
            self.data.pin_vp_y = vp_pos.y()
            logger.log(TRACE, "[chrome-pin] %s ACTIVATE wrote pin_vp=(%.1f,%.1f) from current pos",
                       self._log_id(), self.data.pin_vp_x, self.data.pin_vp_y)
        else:
            # Session restore — rect was serialised in screen-pixel space
            # (saved while pinned) so IIT on renders it correctly without
            # any rescale. pin_vp was also saved in screen pixels.
            logger.log(TRACE, "[chrome-pin] %s ACTIVATE preserving saved pin_vp=(%.1f,%.1f)",
                       self._log_id(), self.data.pin_vp_x, self.data.pin_vp_y)
        # IIT on AFTER the rescale + pin_vp capture so self.pos() / rect
        # reads in mapFromScene happen in the old (scene-unit) frame.
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self._connect_viewport_tracking(view)
        if from_saved_vp:
            # Apply the saved anchor immediately — can't rely on a
            # viewTransformed emission firing after we connected, because
            # camera restore may have fired it before this call ran.
            self._on_viewport_changed()
            logger.log(TRACE, "[chrome-pin] %s ACTIVATE applied saved anchor → scene_pos=(%.1f,%.1f)",
                       self._log_id(), self.pos().x(), self.pos().y())

    def _deactivate_pin(self) -> None:
        """Unpin — node becomes draggable again, moves with the canvas,
        AND scales with the canvas again. Clearing
        ``ItemIgnoresTransformations`` restores the normal scene-item
        rendering so the user can zoom to the node and re-tune its
        rect() to pick the screen size they want frozen on the next
        pin.

        The rect is divided by the current zoom on unpin so the visible
        on-screen size stays continuous across the IIT toggle — the pair
        of this with the rescale in ``_activate_pin`` makes pin/unpin a
        visually silent operation at any zoom level. sync_data() after
        the user resizes while unpinned then stores the new screen-pixel
        target (via the next pin's multiply).
        """
        logger.log(TRACE, "[chrome-pin] %s DEACTIVATE", self._log_id())
        self.data.pinned = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        view = self._get_view()
        zoom = float(getattr(view, 'current_zoom', 1.0)) if view else 1.0
        if not zoom:
            zoom = 1.0
        if zoom != 1.0:
            cur = self.rect()
            self.prepareGeometryChange()
            self.setRect(QRectF(cur.topLeft(),
                                QSizeF(cur.width()  / zoom,
                                       cur.height() / zoom)))
            logger.log(TRACE, "[chrome-pin] %s DEACTIVATE rescaled rect ÷%.3f (zoom) → (%.1f,%.1f)",
                       self._log_id(), zoom, self.rect().width(), self.rect().height())
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
        # Reset paint-time font compensation — under IIT off the view
        # transform handles scaling, so paint_content runs at native pt.
        self.data.pin_scale = 1.0
        self._disconnect_viewport_tracking()

    def _connect_viewport_tracking(self, view) -> None:
        if self._pin_connected:
            logger.log(TRACE, "[chrome-track] %s connect — already connected, skip",
                         self._log_id())
            return
        logger.log(TRACE, "[chrome-track] %s CONNECT viewport tracking", self._log_id())
        if hasattr(view, 'viewTransformed'):
            view.viewTransformed.connect(self._on_viewport_changed)
        view.horizontalScrollBar().valueChanged.connect(self._on_viewport_changed)
        view.verticalScrollBar().valueChanged.connect(self._on_viewport_changed)
        self._pin_connected = True

    def _disconnect_viewport_tracking(self) -> None:
        if not self._pin_connected:
            logger.log(TRACE, "[chrome-track] %s disconnect — not connected, skip",
                         self._log_id())
            return
        logger.log(TRACE, "[chrome-track] %s DISCONNECT viewport tracking", self._log_id())
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
        # Destructor/signal race guard — a transform tick firing into a
        # chromeless node mid-teardown tripped 0xc0000409 (Qt fastfail)
        # on 2026-04-18 (StickerNode); leave these checks in place.
        import shiboken6
        if not shiboken6.isValid(self):
            logger.warning("[chrome-track] %s viewport tick but shiboken says node is INVALID — bail",
                           self._log_id())
            return
        if self._removal_done:
            logger.log(TRACE, "[chrome-track] %s viewport tick but removal_done — bail",
                         self._log_id())
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
    # SHAKE-DELETE
    # ─────────────────────────────────────────────────────────────────────────

    def _on_shake_triggered(self) -> None:
        """Default shake-delete: particle burst + scene removal.

        Subclasses can override to customise (e.g., StickerNode chooses
        between ``sprinkle`` and ``orbital_burst`` based on alpha
        coverage). When overriding, keep the cooldown arm so rapid
        successive shakes don't cascade-delete neighbouring nodes.
        """
        logger.info("[chrome-SHAKE] %s SHAKE TRIGGERED (already_triggered=%s removal_done=%s)",
                    self._log_id(), self._shake_triggered, self._removal_done)
        for i, frame in enumerate(traceback.format_stack()[-12:]):
            for line in frame.rstrip().splitlines():
                logger.info("[chrome-SHAKE] %s   stack[%02d] %s",
                            self._log_id(), i, line)
        if self._shake_triggered:
            logger.log(TRACE, "[chrome-SHAKE] %s BAIL — already triggered", self._log_id())
            return
        self._shake_triggered = True
        scene = self.scene()
        if scene is None:
            logger.warning("[chrome-SHAKE] %s BAIL — no scene", self._log_id())
            return
        from graphics.Particles import sprinkle
        center = self.mapToScene(self.rect().center())
        logger.info("[chrome-SHAKE] %s → sprinkle + arm_cooldown + schedule removeItem",
                    self._log_id())
        sprinkle(scene, center, count=8000)
        arm_cooldown()
        QTimer.singleShot(0, lambda s=scene: s.removeItem(self) if s else None)

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        """Hook scene-leave to trigger the demolition crew.

        QGraphicsRectItem doesn't know about ``_prepare_for_removal`` —
        that's BaseNode's contract. Chromeless nodes use the
        ``ItemSceneChange`` event: when ``value`` is None the item is
        leaving its scene. We hand off to the shared demolition crew
        (same one BaseNode uses), which tolerates missing connections
        / behaviour / buttons / ports and runs the applicable parts of
        the standard sequence. The crew calls our ``_demolition_pre``
        and ``_demolition_post`` hooks at the right points.
        """
        # Log every itemChange — frequent but essential to see the sequence
        # of Qt events around any destructive incident. Skip position-change
        # events (they fire per-mouse-move, would drown the log).
        change_name = _ITEM_CHANGE_NAMES.get(change, f"<{change}>")
        if change_name not in ("ItemPositionChange", "ItemPositionHasChanged",
                               "ItemScenePositionHasChanged"):
            logger.log(TRACE, "[chrome-itemchange] %s change=%s value=%r",
                         self._log_id(), change_name, value)

        if (change == QGraphicsItem.ItemSceneChange and value is None
                and not self._removal_done
                and not getattr(self, '_pinned_across_scenes', False)):
            # THIS is the destructive path — log it loudly with a stack
            # trace so the next cross-node-destruction incident shows
            # exactly what called Qt into telling us we're leaving.
            # Each frame emitted as its own log line because the
            # Rust-backed logger truncates on newline (one log call =
            # one line written). Multi-line stack traces collapse to
            # just the first frame otherwise.
            logger.info("[chrome-DEMOLISH] %s SCENE-LEAVE detected — calling demolish()",
                        self._log_id())
            for i, frame in enumerate(traceback.format_stack()[-20:]):
                for line in frame.rstrip().splitlines():
                    logger.info("[chrome-DEMOLISH] %s   stack[%02d] %s",
                                self._log_id(), i, line)
            self._removal_done = True
            try:
                from nodes._demolition import demolish
                demolish(self)
                logger.info("[chrome-DEMOLISH] %s demolish() returned cleanly",
                            self._log_id())
            except Exception:
                logger.exception("[chrome-DEMOLISH] %s demolish() raised!",
                                 self._log_id())
        elif change == QGraphicsItem.ItemSceneChange and value is not None:
            logger.log(TRACE, "[chrome-scene] %s ENTER scene=%r", self._log_id(), value)
        return super().itemChange(change, value)

    def _demolition_pre(self) -> None:
        """Root-level teardown — disconnect viewport tracking before
        any signal/destructor race can land on us. Called by the
        demolition crew before the main teardown sequence.

        Subclasses extend by overriding and calling ``super()``::

            def _demolition_pre(self):
                super()._demolition_pre()
                self._my_timer.stop()
                self._my_media_player.setSource(QUrl())
                ...
        """
        logger.log(TRACE, "[chrome-demolish-pre] %s entering (_pin_connected=%s)",
                   self._log_id(), self._pin_connected)
        self._disconnect_viewport_tracking()
        logger.log(TRACE, "[chrome-demolish-pre] %s done", self._log_id())

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT — deliberately empty
    # ─────────────────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Chromeless root paints nothing. Every subclass owns its full
        visual — override this method entirely (no super() call required).
        """
        pass
