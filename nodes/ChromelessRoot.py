#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/ChromelessRoot.py ChromelessRoot base class
-Common ancestor for the chromeless family — pin, shake, context menu for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem

from data.ChromelessRootData import ChromelessRootData
from nodes._shake_detect import ShakeDetector, arm_cooldown
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("chromeless")


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

        # Default interaction flags. Pin toggle disables ItemIsMovable
        # while pinned; ItemSendsScenePositionChanges so itemChange gets
        # move/leave events.
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

        # Restore pin state if the data says so — deferred one tick so
        # scene/view are fully constructed by the time we ask.
        if data.pinned:
            QTimer.singleShot(0, self._activate_pin)

    # ─────────────────────────────────────────────────────────────────────────
    # NODE-LIKE CONTRACT (matches BaseNode / StickerNode enough to be interchangeable)
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        """Fold current geometry back into the dataclass — called on
        mouse-release and before serialisation."""
        self.data.x = self.pos().x()
        self.data.y = self.pos().y()
        self.data.width  = self.rect().width()
        self.data.height = self.rect().height()
        self.data.z_value = self.zValue()

    # ─────────────────────────────────────────────────────────────────────────
    # MOUSE HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._show_context_menu(event)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # Arm the shake detector for the duration of this drag.
            self._shake.press()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # Feed the shake detector with the post-move scene position and
        # the view's current zoom, so the shake threshold is
        # zoom-independent.
        zoom = 1.0
        scene = self.scene()
        if scene and scene.views():
            zoom = getattr(scene.views()[0], 'current_zoom', 1.0)
        self._shake.track(self.scenePos(), zoom)

    def mouseReleaseEvent(self, event):
        self._shake.release()
        self.sync_data()
        super().mouseReleaseEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # CONTEXT MENU
    # ─────────────────────────────────────────────────────────────────────────

    def _show_context_menu(self, event) -> None:
        """Right-click menu. The pin toggle is built in at the root;
        subclasses add their own entries via ``_extra_context_menu_items``."""
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
        if self.data.pinned:
            self._deactivate_pin()
        else:
            self._activate_pin()

    def _activate_pin(self) -> None:
        """Pin to current viewport position — disable dragging, record
        viewport anchor, start tracking pan/zoom."""
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
        # Primary: view emits viewTransformed on pan/zoom that mutate
        # the transform matrix directly. Secondary: scrollbars, which
        # only fire when the scene rect grows past the viewport.
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
        # Destructor/signal race guard — a transform tick firing into a
        # chromeless node mid-teardown tripped 0xc0000409 (Qt fastfail)
        # on 2026-04-18 (StickerNode); leave these checks in place.
        import shiboken6
        if not shiboken6.isValid(self):
            return
        if self._removal_done:
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
        if self._shake_triggered:
            return
        self._shake_triggered = True
        scene = self.scene()
        if scene is None:
            return
        from graphics.Particles import sprinkle
        center = self.mapToScene(self.rect().center())
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
        if (change == QGraphicsItem.ItemSceneChange and value is None
                and not self._removal_done):
            self._removal_done = True
            try:
                from nodes._demolition import demolish
                demolish(self)
            except Exception:
                logger.exception("[chromeless] demolish() raised during scene-leave")
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
        self._disconnect_viewport_tracking()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT — deliberately empty
    # ─────────────────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Chromeless root paints nothing. Every subclass owns its full
        visual — override this method entirely (no super() call required).
        """
        pass
