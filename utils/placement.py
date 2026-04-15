#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/placement.py spiral collision placement
-Viewport-aware node placement with outward spiral probe for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF


def spiral_place(scene, node, origin: QPointF | None = None,
                 max_radius: int = 4000, padding: float = 28.0,
                 probes: int = 16,
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
    fallback : QPointF | None
        Position returned when the spiral exhausts its radius without
        finding a clear spot.  ``None`` → *origin*.

    Returns
    -------
    QPointF
        A collision-free position, or *fallback* if the canvas is packed.
    """
    from nodes.BaseNode import BaseNode as _BaseNode

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

    # ── Collision check ─────────────────────────────────────────────────
    def _clear(p: QPointF) -> bool:
        candidate = QRectF(p.x() - padding, p.y() - padding,
                           nw + padding * 2, nh + padding * 2)
        for item in scene.items(candidate):
            if item is node:
                continue
            if isinstance(item, _BaseNode):
                return False
        return True

    # ── Spiral outward ──────────────────────────────────────────────────
    step = max(1, int(max(nw, nh)) // 2)

    if _clear(origin):
        return origin

    for radius in range(step, max_radius, step):
        base = random.uniform(0, 2 * math.pi)
        for k in range(probes):
            angle = base + k * (2 * math.pi / probes)
            candidate = QPointF(
                origin.x() + math.cos(angle) * radius,
                origin.y() + math.sin(angle) * radius,
            )
            if _clear(candidate):
                return candidate

    return fallback
