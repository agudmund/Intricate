#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/placement.py spiral collision placement
-Viewport-aware node placement with outward spiral probe and wire-path awareness for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import logging
import math
import random

from PySide6.QtCore import QPointF, QRectF

_log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# WIRE-PATH AWARENESS
# ─────────────────────────────────────────────────────────────────────────
# Rough-approximation check: when a scatter placement will be wired to a
# parent, verify the wire's straight-line port-to-port path (dilated by
# wire_padding to absorb bezier swell) doesn't cross any unrelated node.
# We never check wire-vs-wire — wires are allowed to cross each other.
# We never do a proper bezier trace — too much load for a probe loop.

def _port_scene_at(node, port, at_pos: 'QPointF | None' = None) -> 'QPointF':
    """Scene position of *port*, either at the node's real position
    (``at_pos=None``) or at a hypothetical position (``at_pos=candidate``).

    ``port.pos()`` is node-local, so hypothetical = at_pos + port.pos()."""
    if at_pos is None:
        return node.mapToScene(port.pos())
    return at_pos + port.pos()


def _closest_port_at(node, ref_scene_pos: 'QPointF',
                     at_pos: 'QPointF | None' = None,
                     input_side: bool = True):
    """Mirror of ``BaseNode.closest_input/output_port`` but allows the node
    to be queried as if it were positioned at ``at_pos``."""
    ports = node.input_ports if input_side else node.output_ports
    best, best_d = ports[0], float('inf')
    for port in ports:
        p = _port_scene_at(node, port, at_pos)
        dx = p.x() - ref_scene_pos.x()
        dy = p.y() - ref_scene_pos.y()
        d = dx * dx + dy * dy
        if d < best_d:
            best_d, best = d, port
    return best


def _segments_intersect(a: 'QPointF', b: 'QPointF',
                        c: 'QPointF', d: 'QPointF') -> bool:
    """Do segments ab and cd properly cross? (CCW sign trick.)"""
    def _ccw(p, q, r):
        return (q.x() - p.x()) * (r.y() - p.y()) - (q.y() - p.y()) * (r.x() - p.x())
    d1 = _ccw(c, d, a)
    d2 = _ccw(c, d, b)
    d3 = _ccw(a, b, c)
    d4 = _ccw(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _segment_crosses_rect(p1: 'QPointF', p2: 'QPointF',
                          rect: QRectF, padding: float) -> bool:
    """Does the line segment p1→p2 (inflated by *padding*) cross *rect*?"""
    inflated = rect.adjusted(-padding, -padding, padding, padding)
    # Quick accept: either endpoint sits inside the inflated rect
    if inflated.contains(p1) or inflated.contains(p2):
        return True
    # Otherwise, proper crossing against any of the 4 rect edges
    corners = (
        QPointF(inflated.left(),  inflated.top()),
        QPointF(inflated.right(), inflated.top()),
        QPointF(inflated.right(), inflated.bottom()),
        QPointF(inflated.left(),  inflated.bottom()),
    )
    for i in range(4):
        if _segments_intersect(p1, p2, corners[i], corners[(i + 1) % 4]):
            return True
    return False


def _wire_path_clear(scene, parent, candidate_pos: QPointF, new_node,
                     wire_padding: float) -> bool:
    """True if the wire from *parent*'s output port to *new_node* (placed at
    *candidate_pos*) doesn't cross any unrelated node.

    Port selection mirrors the live-wire picker in ``Connection._compute_*`` —
    same mechanism that chooses which of the 8 ports the wire hooks onto
    as nodes drift.  Uses a straight-line raycast with a padding margin to
    absorb the bezier's heart-swell; not exact but correct enough for a
    probe loop."""
    if parent is None:
        return True

    parent_centre = parent.mapToScene(parent.rect().center())
    new_rect = new_node.rect()
    new_centre = QPointF(candidate_pos.x() + new_rect.width() / 2.0,
                         candidate_pos.y() + new_rect.height() / 2.0)

    # Port picks use the same logic the live wire uses
    src_port = _closest_port_at(parent, new_centre, at_pos=None, input_side=False)
    dst_port = _closest_port_at(new_node, parent_centre, at_pos=candidate_pos, input_side=True)

    src_pos = parent.mapToScene(src_port.pos())
    dst_pos = candidate_pos + dst_port.pos()

    # Narrow scene query to just the segment's bounding box (inflated) —
    # much faster than iterating every item in a dense scene.
    seg_bbox = QRectF(
        min(src_pos.x(), dst_pos.x()) - wire_padding,
        min(src_pos.y(), dst_pos.y()) - wire_padding,
        abs(dst_pos.x() - src_pos.x()) + wire_padding * 2,
        abs(dst_pos.y() - src_pos.y()) + wire_padding * 2,
    )

    for item in scene.items(seg_bbox):
        if item is new_node or item is parent:
            continue
        if not (hasattr(item, 'data') and hasattr(item, 'to_dict')):
            continue
        if _segment_crosses_rect(src_pos, dst_pos, item.sceneBoundingRect(), wire_padding):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────
# SPIRAL PLACEMENT
# ─────────────────────────────────────────────────────────────────────────

def spiral_place(scene, node, origin: QPointF | None = None,
                 max_radius: int = 4000, padding: float = 28.0,
                 probes: int = 16,
                 max_attempts: int = 50,
                 parent=None, wire_padding: float = 18.0,
                 fallback: QPointF | None = None) -> QPointF:
    """Find a clear position for *node* on *scene* using spiral probing.

    Parameters
    ----------
    scene : IntricateScene
        The graphics scene containing all nodes.
    node : BaseNode
        The node to place — must already be added to the scene (even
        off-screen) so its rect() returns a valid size.
    origin : QPointF | None
        Centre of the spiral search.  ``None`` → viewport centre if a
        view exists, else (0, 0).
    max_radius : int
        Hard ceiling on how far the spiral expands (px).  When a view
        exists this is overridden to 2.5× the viewport diagonal.
    padding : float
        Breathing room around each candidate rect (px).
    probes : int
        Number of evenly-spaced angles tested per ring.
    max_attempts : int
        Budget of total probes before giving up and returning the best
        fallback candidate found.  Prevents infinite recursion when no
        wire-clear seat exists anywhere on the canvas.
    parent : BaseNode | None
        If supplied, the placement also rejects seats where the wire
        from *parent* to the new node would cross an unrelated node.
        Wire-vs-wire crossings are always allowed.  When all attempts
        produce wire-crossings, the first node-clear-but-wire-crosses
        candidate is used as a graceful-failure fallback.
    wire_padding : float
        Thickness added to the wire's straight-line raycast (px) — wide
        enough to absorb the bezier's heart-swell.
    fallback : QPointF | None
        Position returned when the canvas is so packed that even node
        collision can't be avoided.  ``None`` → *origin*.

    Returns
    -------
    QPointF
        A collision-free (and wire-clear, when *parent* is supplied)
        position, or a graceful-failure seat if the budget runs out.
    """
    nr = node.rect()
    nw, nh = nr.width(), nr.height()

    # ── Resolve origin from viewport when not provided ──────────────────
    views = scene.views()
    if origin is None:
        if views:
            view = views[0]
            vr = view.mapToScene(view.viewport().rect()).boundingRect()
            origin = vr.center()
        else:
            origin = QPointF(0, 0)

    # Scale max_radius to viewport when available
    if views:
        view = views[0]
        vr = view.mapToScene(view.viewport().rect()).boundingRect()
        max_radius = int(max(vr.width(), vr.height()) * 2.5)

    if fallback is None:
        fallback = origin

    # ── Node-on-node collision check ─────────────────────────────────────
    # Duck-typed across node roots: BaseNode variants and StickerNode
    # (2026-04-18 split).  Any future root that carries `.data` and
    # `.to_dict()` is treated as a real canvas item for placement.
    def _node_clear(p: QPointF) -> bool:
        candidate = QRectF(p.x() - padding, p.y() - padding,
                           nw + padding * 2, nh + padding * 2)
        for item in scene.items(candidate):
            if item is node:
                continue
            if hasattr(item, 'data') and hasattr(item, 'to_dict'):
                return False
        return True

    # ── Probe + fallback tracking ────────────────────────────────────────
    # attempts counts EVERY probe (including node-colliding ones) so the
    # budget truncates runaway spirals in dense canvases.
    state = {'attempts': 0, 'best_wire_crosser': None}

    def _try(p: QPointF) -> bool:
        state['attempts'] += 1
        _log.log(5, "[scatter] probe %d @(%.0f,%.0f)",
                 state['attempts'], p.x(), p.y())
        if not _node_clear(p):
            return False
        if _wire_path_clear(scene, parent, p, node, wire_padding):
            return True
        # Node-clear but wire crosses — reserve as graceful-failure fallback
        if state['best_wire_crosser'] is None:
            state['best_wire_crosser'] = p
        return False

    # ── Spiral outward (no directional bias — the random-sample-of-uncertainty
    #    is what gives the scatter its organic character) ─────────────────
    step = max(1, int(max(nw, nh)) // 2)

    if _try(origin):
        _log.debug("[scatter] %s placed at origin after %d attempt%s",
                   node.__class__.__name__, state['attempts'],
                   '' if state['attempts'] == 1 else 's')
        return origin

    for radius in range(step, max_radius, step):
        if state['attempts'] >= max_attempts:
            break
        base = random.uniform(0, 2 * math.pi)
        for k in range(probes):
            if state['attempts'] >= max_attempts:
                break
            angle = base + k * (2 * math.pi / probes)
            candidate = QPointF(
                origin.x() + math.cos(angle) * radius,
                origin.y() + math.sin(angle) * radius,
            )
            if _try(candidate):
                _log.debug("[scatter] %s placed after %d attempts, radius=%d",
                           node.__class__.__name__, state['attempts'], radius)
                return candidate

    # Budget exhausted.  Prefer the reserve over the raw fallback origin —
    # a node-clear-but-wire-crosses seat reads as a choice; a node-on-node
    # overlap reads as corrupt layout.
    if state['best_wire_crosser'] is not None:
        _log.debug("[scatter] %s gave up after %d attempts, using wire-crossing seat",
                   node.__class__.__name__, state['attempts'])
        return state['best_wire_crosser']
    _log.debug("[scatter] %s gave up after %d attempts, falling back to origin",
               node.__class__.__name__, state['attempts'])
    return fallback


def wander_origin(prev_node) -> QPointF:
    """Pick a random anchor point near *prev_node* for the next scatter probe.

    Simulates the organic scatter of sticky notes dropped across a desk —
    mostly clustered within conversational range, occasionally flung further
    out. Callers feed the result to spiral_place() as the *origin* for the
    next node, so the focal point walks across the canvas with every spawn
    instead of fanning out from one fixed centre.

    Tuning mirrors the original MarkdownNode behaviour:
        85 % chance of gaussian cluster at ~260 px (min 120 px)
        15 % chance of an outlier fling at 500–900 px
    """
    pr = prev_node.rect()
    cx = prev_node.pos().x() + pr.width()  / 2.0
    cy = prev_node.pos().y() + pr.height() / 2.0

    angle = random.uniform(0, 2 * math.pi)

    if random.random() < 0.15:
        distance = random.uniform(500, 900)
    else:
        distance = random.gauss(260, 80)
        distance = max(120, distance)

    return QPointF(
        cx + math.cos(angle) * distance,
        cy + math.sin(angle) * distance,
    )


# ─────────────────────────────────────────────────────────────────────────
# CHAIN SPAWN — canonical organic scatter for any node-spawn-from-source flow
# ─────────────────────────────────────────────────────────────────────────

# Far-left-of-everything staging position for nodes that need to be added
# to the scene (so their ``rect()`` is accurate for measurement) before
# the real placement is computed.  Anything outside the viewport works;
# this magnitude is comfortably beyond any reasonable canvas bound and
# was the convention shared across the three split-spawn paths before
# they consolidated here.
OFFSCREEN_STAGING = QPointF(-999_999, -999_999)


def chain_spawn(scene, source_node, items, factory, *,
                connection_factory=None,
                wire_first_to_source: bool = True,
                padding: float = 28.0) -> list:
    """Spawn a chain of nodes from *items*, organically scattered and wired.

    The canonical scatter helper.  Any node type that produces secondary
    or tertiary nodes from itself reaches for this — paste-split,
    button-export, document-explode, ClaudeNode-invents-companions.
    Embodies the orchestration MarkdownNode pioneered: offscreen staging
    so the spawn never flashes at (0, 0); ``raise_node`` for z-order;
    snug auto-fit (title-width before height because body wrap depends
    on the current width); ``wander_origin`` → ``spiral_place`` with
    parent collision avoidance for the wire path.  The deliberate
    asymmetry of the result comes from spiral_place's random base
    angle per ring and wander_origin's 85/15 cluster-vs-fling — two
    identical trees from the same input is roughly impossible.

    Parameters
    ----------
    scene
        IntricateScene that will own the spawned nodes.
    source_node
        Originating node — the chain anchor.  ``prev_node`` for the
        first ``wander_origin`` call; first spawn wires back to it
        when *wire_first_to_source* is True.
    items
        Iterable of opaque values, each fed to *factory*.
    factory
        Callable ``item -> BaseNode | None``.  Returning None skips
        the item — useful with predicate-dispatcher factories that
        filter structural-only or otherwise unsuitable content.
    connection_factory
        Callable ``(prev, new) -> Connection``.  Default constructs
        ``graphics.Connection.Connection`` directly (deferred import
        so this module stays graphics-free at top level).
    wire_first_to_source
        When True (default), the first spawned node wires back to
        *source_node* — the right behaviour for paste-split / button-
        export flows where the source stays visible after spawning.
        When False, the first spawned node has no incoming wire — the
        right behaviour for zombie-spawn flows (MarkdownNode self-
        vaporises after splitting), where wiring to the source would
        dangle.
    padding
        Spiral-place padding (px).  Default matches spiral_place's
        own default; surfaced here so callers with tighter chrome
        can tune.

    Returns
    -------
    list of BaseNode
        Spawned nodes in chain order, factory-skipped items omitted.
    """
    if connection_factory is None:
        from graphics.Connection import Connection
        connection_factory = Connection

    # Mirror the canonical bulk-adds protections used by Scene.load_session
    # and Scene.import_session — raise the scene's _bulk_adding counter so
    # peer NodeBehaviour pulse/bg-anim ticks and Connection glide ticks
    # early-return for the duration of the spawn loop, and yield to the
    # event loop periodically so the UI thread stays responsive on chains
    # of thousands.  See Scene.py:~1078 for the load_session reference.
    # Without this the splitter freezes the UI proportional to
    # paragraphs × existing peer count (Documents/Compliance/Warm Splitter
    # Hang Investigation.md).
    #
    # NOTE: load_session and import_session use ExcludeUserInputEvents
    # because they run on a not-yet-shown / mid-import scene where user
    # clicks would land in undefined state.  chain_spawn runs on a live,
    # already-shown scene during a deliberate user action (paste-split,
    # cushions-export); the user must remain able to scroll, zoom, drag,
    # and otherwise interact during a long chain.  AllEvents is correct
    # here — the gate handles peer animation quiescence; user input just
    # needs to flow through.
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication
    _YIELD_EVERY     = 5
    _YIELD_BUDGET_MS = 50

    scene._bulk_adding = getattr(scene, '_bulk_adding', 0) + 1
    spawned: list = []
    prev_node = source_node

    try:
        for i, item in enumerate(items):
            node = factory(item)
            if node is None:
                continue

            node.setPos(OFFSCREEN_STAGING)
            scene.addItem(node)
            scene.raise_node(node)

            # Title-width first because body wrapping depends on the current
            # width.  Both fits are guarded by hasattr so node types without
            # them (chromeless StickerNode descendants, future minimalist
            # types) silently keep their default geometry.
            if hasattr(node, '_auto_fit_title_width'):
                node._auto_fit_title_width()
            if hasattr(node, '_auto_fit_height'):
                node._auto_fit_height(shrink=True)

            chain_origin = wander_origin(prev_node)
            pos = spiral_place(
                scene, node, origin=chain_origin,
                parent=prev_node, fallback=chain_origin,
                padding=padding,
            )
            node.setPos(pos)

            is_first_spawn = (len(spawned) == 0)
            if not is_first_spawn or wire_first_to_source:
                conn = connection_factory(prev_node, node)
                scene.addItem(conn)

            spawned.append(node)
            prev_node = node

            if (i + 1) % _YIELD_EVERY == 0:
                QApplication.processEvents(
                    QEventLoop.AllEvents, _YIELD_BUDGET_MS,
                )
    finally:
        scene._bulk_adding = max(0, getattr(scene, '_bulk_adding', 1) - 1)

    return spawned
