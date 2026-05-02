#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - graphics/View.py IntricateView class
-The window into the world. Renders the scene, handles navigation and OS drops for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QCursor, QGuiApplication


_IMAGE_EXTENSIONS   = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
_VIDEO_EXTENSIONS   = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv", ".m4v"}
_AUDIO_EXTENSIONS   = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma"}
_SESSION_EXTENSIONS = {".json", ".jsonl", ".intricate"}
_CODE_EXTENSIONS    = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json", ".xml",
    ".yaml", ".yml", ".toml", ".sh", ".bat", ".sql", ".md", ".txt",
    ".cfg", ".ini", ".log", ".r", ".swift", ".kt", ".lua", ".pl",
}


class IntricateView(QGraphicsView):
    """
    The viewport into IntricateScene.

    Responsibilities:
        - Renders the scene with correct background and antialiasing
        - Handles pan (middle mouse) and zoom (wheel, cursor-anchored)
        - Receives OS drag-and-drop events and routes image files to the scene

    Navigation ledger:
        current_zoom tracks the applied scale factor — single source of truth
        for zoom limits and any external camera sync.

    Drag and drop:
        Image files dragged from Explorer land here. The view maps the drop
        position to scene coordinates and delegates to scene.add_image_node().
        Multiple files dropped together are staggered so they don't overlap.
    """

    # Zoom-out floor extended in two passes:
    #   2026-04-18: 0.10 → 0.03 (3×) — accommodate large auto-split chains
    #               from WarmNode paste-splits, once a 5 MB paste became
    #               100+ chained nodes.
    #   2026-05-02: 0.03 → 0.01 (3×, total 10× from original) — the aerial
    #               cream strip now provides a visibility floor regardless
    #               of zoom (see Documents/Design/Zoom Level.md), so the
    #               canvas reads as a constellation of node positions at
    #               any altitude. With the floor decoupled from the
    #               legibility constraint, ZOOM_MIN can be pushed wherever
    #               the user needs to fit the whole tree shape on screen.
    #               0.01 = 100× zoomed out, enough headroom for thousand-
    #               node chains while leaving the aerial-swap threshold
    #               (currently 0.07) plenty of range to play with.
    ZOOM_MIN = 0.01
    ZOOM_MAX = 5.0

    # Emitted after any transform mutation (pan, zoom, programmatic scale /
    # translate). Qt does not provide a native transform-change signal, and
    # pan-by-translate never moves the scrollbars, so viewport-pinned items
    # (StickerNode when pinned, any future screen-space overlay) need this
    # channel to stay anchored as the canvas moves beneath them. Emits only
    # on actual transform changes — no timer, no per-paint polling.
    viewTransformed = Signal()

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)

        self.current_zoom  = 1.0
        import shared_braincell.settings as _s
        self._blur_alpha   = int(_s.get_nested("intricate", "canvas", "blur_alpha", 180))   # driven by sidebar blur slider (0=clear, 255=opaque)
        self._last_pan_pos: QPointF | None = None
        self._on_zoom_changed = None   # optional callback, set by main_window

        # Alt+Right-click drag zoom (Photoshop-style)
        self._alt_zooming      = False
        self._alt_zoom_start_y = 0.0

        self._configure()

    def _configure(self) -> None:
        # ── Frame ─────────────────────────────────────────────────────────────
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setLineWidth(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.viewport().setContentsMargins(0, 0, 0, 0)

        # ── Transparency — let the DWM blur show through ─────────────────────
        self.viewport().setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # ── Scrollbars ────────────────────────────────────────────────────────
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ── Transform anchors ─────────────────────────────────────────────────
        # NoAnchor — we control camera position explicitly, Qt does not help.
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # ── Paint quality ─────────────────────────────────────────────────────
        # MinimalViewportUpdate: only repaints dirty regions.  During pan, Qt
        # uses a bitblt scroll (very cheap) plus repaints only the newly-exposed
        # strip — no full-viewport repaint on every mouse-move tick.
        # FullViewportUpdate required for WA_TranslucentBackground — partial
        # repaints leave stale alpha fragments in the composited background.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing)

        # ── Focus ─────────────────────────────────────────────────────────────
        # NoFocus prevents the view from stealing keyboard focus from toolbar
        # widgets. Key events are routed explicitly when needed.
        self.setFocusPolicy(Qt.NoFocus)

        # ── Drag and drop ─────────────────────────────────────────────────────
        self.setAcceptDrops(True)

    # ─────────────────────────────────────────────────────────────────────────
    # TRANSFORM EMISSION
    # Overriding scale() and translate() is the passive "single source of
    # truth" pattern: every transform mutation — whether from pan, wheel
    # zoom, Alt+drag zoom, or a programmatic caller — flows through these
    # two methods, so a single emit at each point catches all of it. No
    # polling, no per-paint work, no dedicated timer.
    # ─────────────────────────────────────────────────────────────────────────

    def scale(self, sx, sy):
        super().scale(sx, sy)
        self.viewTransformed.emit()

    def translate(self, dx, dy):
        super().translate(dx, dy)
        self.viewTransformed.emit()

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect) -> None:
        """Frost-tinted canvas background — alpha-blended over the DWM blur."""
        painter.save()
        painter.resetTransform()
        c = QColor(Theme.backDrop)
        c.setAlpha(self._blur_alpha)
        painter.fillRect(self.viewport().rect(), c)
        painter.restore()

    def drawForeground(self, painter: QPainter, rect) -> None:
        """Rounded border overlaying the viewport edges — matches node bevel style."""
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing)

        vr = self.viewport().rect()
        radius = Theme.nodeRoundRadius
        bw = Theme.nodeBorderWidth

        outer = QPainterPath()
        outer.addRoundedRect(vr.adjusted(0, 0, 0, 0), radius, radius)

        # Paint the four corner slivers (outside the rounded rect) with the
        # window background so nodes dragged near the edge don't bleed through.
        full = QPainterPath()
        full.addRect(vr)
        corners = full.subtracted(outer)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Theme.windowBg))
        painter.drawPath(corners)

        # Border strip — drawn on top of the corners.
        inner = QPainterPath()
        inner.addRoundedRect(
            vr.adjusted(bw, bw, -bw, -bw),
            max(0, radius - bw), max(0, radius - bw),
        )
        border_strip = outer.subtracted(inner)

        painter.setBrush(QColor(Theme.primaryBorder))
        painter.drawPath(border_strip)
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_zoom(self, factor: float, anchor: QPointF | None = None) -> None:
        """
        Apply a zoom factor clamped to [ZOOM_MIN, ZOOM_MAX].
        If anchor is provided the scene point under that position stays fixed.
        """
        new_zoom = self.current_zoom * factor
        if not (self.ZOOM_MIN <= new_zoom <= self.ZOOM_MAX):
            return

        if anchor is not None:
            old_vp = self.mapFromScene(anchor)
            self.scale(factor, factor)
            new_vp = self.mapFromScene(anchor)
            delta  = new_vp - old_vp
            zoom   = self.transform().m11()
            self.translate(-delta.x() / zoom, -delta.y() / zoom)
        else:
            self.scale(factor, factor)

        self.current_zoom = new_zoom
        if self._on_zoom_changed:
            self._on_zoom_changed()

    def _notify_viewport_changed(self) -> None:
        """Tell the scene the visible area moved so it can cull offscreen videos.
        Skips while curtains are collapsed — videos stay paused until expand."""
        win = self.window()
        if win and getattr(win, 'is_collapsed', False):
            return
        scene = self.scene()
        if scene and hasattr(scene, 'update_video_visibility'):
            viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            scene.update_video_visibility(viewport_rect)

    def wheelEvent(self, event) -> None:
        """Zoom anchored to the cursor position."""
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        anchor = self.mapToScene(event.position().toPoint())
        self._apply_zoom(factor, anchor=anchor)
        self._notify_viewport_changed()
        event.accept()

    # ─────────────────────────────────────────────────────────────────────────
    # SNIP MODE  — one-shot wire deletion
    # ─────────────────────────────────────────────────────────────────────────

    _snip_mode = False

    def start_snip_mode(self) -> None:
        """Enter wire-snip mode: cursor becomes the delete icon, next wire click removes it."""
        self._snip_mode = True
        cursor_pix = Theme.icon(Theme.iconSnipCursor, fallback_color="#c07070") \
                         .scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.viewport().setCursor(QCursor(cursor_pix, 16, 16))

    def end_snip_mode(self) -> None:
        """Exit wire-snip mode and restore the default cursor."""
        self._snip_mode = False
        self.viewport().unsetCursor()

    def _try_snip_at(self, scene_pos) -> bool:
        """Hit-test for a Connection near scene_pos, remove it, return True if found."""
        from graphics.Connection import Connection
        from PySide6.QtCore import QRectF
        # Wires are thin bezier paths — use a tolerance rect so the click doesn't
        # have to land on the exact sub-pixel centre of the curve.
        tol = 10.0 / self.current_zoom
        hit_rect = QRectF(scene_pos.x() - tol, scene_pos.y() - tol, tol * 2, tol * 2)
        conn = next(
            (item for item in self.scene().items(hit_rect)
             if isinstance(item, Connection)),
            None,
        )
        if conn is None:
            return False
        try:    conn.start_node.connections.remove(conn)
        except ValueError: pass
        try:    conn.end_node.connections.remove(conn)
        except (ValueError, AttributeError): pass
        self.scene().removeItem(conn)
        return True

    def mousePressEvent(self, event) -> None:
        """Start pan on middle mouse. Route clicks when a floating wire is active."""
        if self._snip_mode:
            if event.button() in (Qt.LeftButton, Qt.RightButton):
                if event.button() == Qt.LeftButton:
                    scene_pos = self.mapToScene(event.position().toPoint())
                    self._try_snip_at(scene_pos)
                self.end_snip_mode()
                event.accept()
                return

        self.setFocus()
        # Safety net: clear any stale scene mouse grabber left behind by a
        # removed or zombie node.  Runs on EVERY press (left, middle, right,
        # alt-zoom) — not just middle-mouse — so no early-return path can
        # skip it.  A grabber is stale if it left the scene entirely, OR if
        # its interaction flags were zeroed by _prepare_for_removal Phase 0
        # while it's still technically in the scene (deferred-removal window).
        scene = self.scene()
        if scene:
            grabber = scene.mouseGrabberItem()
            if grabber and (
                grabber.scene() is None
                or not grabber.flags()
            ):
                grabber.ungrabMouse()
        # Alt+Right-click → Photoshop-style drag zoom.
        # `event.modifiers()` is the modifier state Qt cached with the event;
        # on Windows it sometimes drops the Alt bit (focus changes, IME swaps,
        # global hooks all interfere). `QGuiApplication.queryKeyboardModifiers()`
        # polls the OS keyboard state live, so it stays honest. OR them so the
        # check fires whenever Alt is genuinely held — whichever path Qt
        # remembered it through. (2026-04-29: alt-zoom regressed because
        # event.modifiers() started reporting alt:False against a held Alt key;
        # the live-poll fallback closes that class of failure permanently.)
        mods = event.modifiers() | QGuiApplication.queryKeyboardModifiers()
        if event.button() == Qt.RightButton and mods & Qt.AltModifier:
            self._alt_zooming = True
            self._alt_zoom_start_y = event.position().y()
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = event.position()
            self.setRenderHint(QPainter.Antialiasing, False)
            event.accept()
            return
        scene = self.scene()
        if scene and getattr(scene, '_floating_conn', None):
            if event.button() == Qt.RightButton:
                scene.cancel_connection()
                event.accept()
                return
            if event.button() == Qt.LeftButton:
                scene_pos = self.mapToScene(event.position().toPoint())
                # Use items() not itemAt() — itemAt can return the parent node
                # instead of the Port child when they share the same area
                from nodes.Port import Port
                input_port = next(
                    (i for i in scene.items(scene_pos)
                     if isinstance(i, Port) and not i.is_output),
                    None
                )
                if input_port:
                    scene.complete_connection(input_port.parent_node,
                                              explicit_port=input_port)
                else:
                    # No port hit — snap to the closest input port on whatever
                    # node is under the cursor; dynamic corner routing handles the rest
                    node = next(
                        (i for i in scene.items(scene_pos)
                         if hasattr(i, 'input_ports') and i.input_ports),
                        None
                    )
                    if node:
                        scene.complete_connection(node)
                    else:
                        scene.cancel_connection()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Pan on middle mouse drag; Alt+Right drag zoom; update floating wire on move."""
        if self._alt_zooming and event.buttons() & Qt.RightButton:
            delta_y = event.position().y() - self._alt_zoom_start_y
            factor = 1.005 ** (-delta_y)   # up = zoom in, gentle sensitivity
            anchor = self.mapToScene(event.position().toPoint())
            self._apply_zoom(factor, anchor=anchor)
            self._alt_zoom_start_y = event.position().y()
            event.accept()
            return
        if self._last_pan_pos is not None and event.buttons() & Qt.MiddleButton:
            delta          = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            zoom           = self.transform().m11()
            self.translate(delta.x() / zoom, delta.y() / zoom)
            event.accept()
            return
        scene = self.scene()
        if scene and getattr(scene, '_floating_conn', None):
            scene_pos = self.mapToScene(event.position().toPoint())
            scene.update_floating_connection(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """End pan/zoom; expand the scene rect if a node was dragged outside it."""
        if event.button() == Qt.RightButton and self._alt_zooming:
            self._alt_zooming = False
            self.setCursor(Qt.ArrowCursor)
            # Alt-drag zoom ended — re-evaluate viewport culling + tiny-render
            # pause so videos that were scaled down to imperceptible on-screen
            # size during the drag settle into the pause state.
            self._notify_viewport_changed()
            event.accept()
            return
        if event.button() == Qt.MiddleButton:
            self._last_pan_pos = None
            self.setRenderHint(QPainter.Antialiasing, True)
            self._notify_viewport_changed()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            # Defer to next event loop tick — scene state is fully settled by then
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._expand_scene_rect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._notify_viewport_changed()

    # ── Scene auto-expansion ──────────────────────────────────────────────────
    #
    # The canvas starts tiny (1000×1000 from Scene.__init__) and grows only
    # when a node's outer edge lands at or past the current sceneRect boundary.
    # This keeps memory/paint cost proportional to what the user has actually
    # built — a fresh session is near-free, and gigantic networks only pay for
    # the space they occupy.
    #
    # Trimming is implicit: sessions don't persist sceneRect, so a reload
    # starts from Scene.__init__'s default and re-expands to fit current
    # contents only. Delete half your nodes, reload, the rect is lean again.
    #
    # The margin added beyond the outermost node is NOT a fixed constant —
    # it's a viewport-aware buffer so that any edge node can be panned into
    # the centre of the view at roughly the zoom it was placed at. Without
    # this buffer, edge nodes can only be scrolled to the viewport edge,
    # never centred (the historical workaround was dropping a throwaway node
    # half a screen offscreen to force expansion, then deleting it).
    #
    # Zoom itself never triggers expansion — only node placement/move/drop
    # does. So sampling the current zoom here is a one-shot read at the
    # moment of expansion, not a per-frame cost during pan/zoom.

    _MIN_CENTER_MARGIN = 700   # floor (scene px) — ≈ half a 1080p viewport at 1.0 zoom

    def _expansion_margin(self) -> float:
        """
        Half the viewport expressed in scene coordinates at the current zoom,
        floored at _MIN_CENTER_MARGIN. This is how much breathing room we add
        beyond the outermost node so that edge nodes can be centred in the
        viewport rather than pinned to its edge.
        """
        zoom = self.transform().m11() or 1.0
        half_vp_scene = (self.viewport().width() / 2.0) / zoom
        return max(half_vp_scene, float(self._MIN_CENTER_MARGIN))

    def _expand_scene_rect(self) -> None:
        """
        Grow the scene rect to encompass all nodes plus a zoom-aware margin
        (see _expansion_margin). Only measures nodes (not wires) — wire paths
        overshoot into nodes and would inflate the rect incorrectly. Never
        shrinks; uses united().
        """
        scene = self.scene()
        if not scene:
            return
        from PySide6.QtCore import QRectF
        nodes_rect = QRectF()
        for item in scene.items():
            if hasattr(item, 'data') and hasattr(item, 'rect'):
                nodes_rect = nodes_rect.united(item.mapRectToScene(item.rect()))
        if nodes_rect.isNull():
            return
        m = self._expansion_margin()
        new_rect = scene.sceneRect().united(nodes_rect.adjusted(-m, -m, m, m))
        if new_rect != scene.sceneRect():
            scene.setSceneRect(new_rect)

    # ─────────────────────────────────────────────────────────────────────────
    # DRAG AND DROP
    # ─────────────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        """Accept drags that contain at least one supported image or video file."""
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            supported = _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _AUDIO_EXTENSIONS | _SESSION_EXTENSIONS | _CODE_EXTENSIONS | {".qss"}
            if any(Path(p).suffix.lower() in supported for p in paths):
                event.acceptProposedAction()
                return
        # Let Qt route internal drags (e.g. palette swatches, text selection
        # inside proxy widgets) through the normal QGraphicsView pipeline.
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """Keep accepting during the drag so the cursor stays correct."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        """
        Map the drop position to scene coordinates and create nodes.

        Multiple files are scattered via spiral_place so they land in
        collision-free spots around the drop point instead of piling up.
        Unsupported files in a multi-file drop are silently skipped.
        """
        if event.mimeData().hasFormat("application/x-intricate-palette-color"):
            super().dropEvent(event)
            return
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        # Map drop viewport position → scene coordinates (QPointF all the way)
        drop_scene_pos = self.mapToScene(event.position().toPoint())

        from utils.placement import spiral_place, wander_origin

        prev_node = None

        def _scatter(node):
            """Ease a freshly-added node via spiral probe.

            First node anchors at the drop point; every subsequent node
            anchors at a wander_origin based on the previous node so the
            focal point walks across the canvas — the MarkdownNode pattern.
            Without this, all drops fan out in concentric probe rings from
            one fixed centre and look suspiciously uniform.

            Satellite nodes already connected at scatter time (e.g. the
            caption AboutNode that ImageNode.load_from_path spawns during
            the node factory call) get dragged along by the same delta so
            they don't orphan at the original drop point.
            """
            nonlocal prev_node
            if node is None:
                return
            try:
                if prev_node is None:
                    origin = drop_scene_pos
                else:
                    origin = wander_origin(prev_node)
                old_pos = node.pos()
                new_pos = spiral_place(self.scene(), node, origin=origin, fallback=origin)
                delta = new_pos - old_pos
                node.setPos(new_pos)
                # Bring along auto-spawned satellites. At this moment the node
                # has only just been created, so anything connected to it must
                # be a satellite the factory spawned — no user wiring yet.
                for conn in list(getattr(node, 'connections', [])):
                    try:
                        other = conn.end_node if conn.start_node is node else conn.start_node
                    except RuntimeError:
                        continue
                    if other is not None and other is not node:
                        other.setPos(other.pos() + delta)
                prev_node = node
            except Exception:
                pass

        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext  = Path(path).suffix.lower()
            scene = self.scene()
            if not scene:
                continue
            if ext in _AUDIO_EXTENSIONS and hasattr(scene, 'add_audio_node'):
                node = scene.add_audio_node(pos=drop_scene_pos)
                node.load_from_path(path)
                _scatter(node)
            elif ext in _VIDEO_EXTENSIONS and hasattr(scene, 'add_video_node'):
                node = scene.add_video_node(pos=drop_scene_pos, path=path)
                _scatter(node)
            elif ext in _IMAGE_EXTENSIONS and hasattr(scene, 'add_image_node'):
                node = scene.add_image_node(pos=drop_scene_pos, path=path)
                _scatter(node)
            elif ext in _SESSION_EXTENSIONS and hasattr(scene, 'add_session_node'):
                node = scene.add_session_node(pos=drop_scene_pos, source_path=path)
                _scatter(node)
            elif ext == ".qss" and hasattr(scene, 'add_palette_node'):
                colors = self._parse_qss_colors(path)
                if colors:
                    node = scene.add_palette_node(pos=drop_scene_pos, colors=colors)
                    _scatter(node)
            elif ext in _CODE_EXTENSIONS and hasattr(scene, 'add_code_node'):
                # .py files with hex colors → palette node + code node
                if ext == ".py" and hasattr(scene, 'add_palette_node'):
                    colors = self._parse_qss_colors(path)
                    if colors:
                        pnode = scene.add_palette_node(pos=drop_scene_pos, colors=colors)
                        _scatter(pnode)
                node = scene.add_code_node(pos=drop_scene_pos, path=path)
                _scatter(node)

        event.acceptProposedAction()

    @staticmethod
    def _parse_qss_colors(path: str) -> list:
        """Extract unique hex colors from a .qss file as palette-ready dicts."""
        import re
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        raw = re.findall(r'#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', text)
        seen = set()
        colors = []
        for h in raw:
            if h.lower() not in seen:
                seen.add(h.lower())
                colors.append({"label": h, "hex": h})
        return colors


# Theme import at bottom — View.py is part of the graphics package and
# Theme lives there too. Deferred to avoid any circular import risk at
# package initialisation time.
from pretty_widgets.graphics.Theme import Theme
from pathlib import Path
