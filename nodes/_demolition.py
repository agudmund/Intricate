#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/_demolition.py the demolition crew
-Separate crew for taking things down safely, called when a node is leaving
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# ─────────────────────────────────────────────────────────────────────────────
# THE DEMOLITION CREW
# ─────────────────────────────────────────────────────────────────────────────
#
# Construction and demolition are different professions.  Carpenters do not
# carry dynamite in their toolboxes.  A node's job is to build its thing,
# paint its content, respond to the user.  When the user is done with it,
# the demolition crew arrives — the crew that knows the procedure for
# severing Qt signals, detaching proxies, stopping timers, nulling refs,
# and invalidating paint regions without crashing the process.
#
# Nodes hand the crew a label — a class-level manifest listing what needs
# to come down — and the crew reads it.  For anything too bespoke to
# declare (GitNode dismissing its loading plushie, VideoNode's deferred
# media-player teardown), the node can implement `_demolition_pre` and
# `_demolition_post` hooks that run before and after the crew's standard
# sequence.
#
# Declarative manifest (all optional, declared as class attributes):
#
#   _demolition_proxies: list[str]
#       Attr names of QGraphicsProxyWidget children to tear down in
#       canonical order: setWidget(None) → widget.setParent(None) +
#       deleteLater() → scene.removeItem(proxy) → null.  Scene rects are
#       captured before teardown and explicitly invalidated afterwards.
#
#   _demolition_timers: list[tuple[str, str | None]]
#       Pairs of (timer_attr, slot_method_name).  Crew stops the timer,
#       disconnects timeout from slot if slot name is given, else
#       disconnects everything from timeout.  None attr is skipped.
#
#   _demolition_animations: list[tuple[str, list[str]]]
#       Pairs of (anim_attr, list_of_signal_names_to_disconnect).
#       Signal names like "valueChanged", "finished".  Crew calls stop()
#       then disconnects each named signal.
#
#   _demolition_thread_flag: str | None
#       Attribute name of a bool cancellation flag for a background
#       thread.  Crew sets it to True FIRST so the thread bails before
#       any timer / proxy teardown writes to soon-to-be-dead state.
#
#   _demolition_media_players: list[str]
#       Attr names of QMediaPlayer objects.  Crew calls stop(),
#       setVideoOutput(None), setAudioOutput(None), deleteLater().
#
#   _demolition_workers: list[tuple[str, list[str]]]
#       Pairs of (worker_attr, signal_names).  Crew disconnects each
#       named signal on the worker.  Does not call deleteLater — the
#       worker's Qt parent typically owns that lifetime.
#
# Pre/post hooks (optional methods on the node):
#
#   def _demolition_pre(self) -> None:
#       Runs FIRST, before the crew's standard sequence.  For work that
#       must be synchronous and must happen before Qt invalidates the
#       node's state.  Examples: GitNode._dismiss_loading_node,
#       StickerNode._disconnect_viewport_tracking.
#
#   def _demolition_post(self) -> None:
#       Runs LAST, after the crew's sequence is complete.  Rarely needed.
#       Use for state that depends on the node being fully torn down.
#
# ─────────────────────────────────────────────────────────────────────────────

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGraphicsItem
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("demolition")


def demolish(node) -> None:
    """Tear a node down safely. Idempotent: a second call is a no-op.

    Called from the node's `_prepare_for_removal` (or directly from
    `itemChange` for non-BaseNode roots like StickerNode).  Drives the
    entire teardown sequence: pre-hook, standard phases, manifest walks,
    post-hook.  Every step is defensive — missing attributes, dead Qt
    objects, and absent scene refs are all handled without raising.
    """
    if getattr(node, '_removal_done', False):
        return
    node._removal_done = True

    tag = _tag(node)
    logger.log(5, "[DEMO] %s crew arriving — _demolition_pre", tag)

    # ── Pre-hook: bespoke node-specific work ──────────────────────────
    if hasattr(node, '_demolition_pre'):
        try:
            node._demolition_pre()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} _demolition_pre raised: {exc}")

    # ── Thread flag: set FIRST so background workers bail before any
    #    of the Qt-side teardown writes to soon-to-die state ──────────
    flag_attr = getattr(type(node), '_demolition_thread_flag', None)
    if flag_attr:
        try:
            setattr(node, flag_attr, True)
        except Exception:
            pass

    # ── Phase 0: paint-cache flush + scene invalidate + flag zero ─────
    logger.log(5, "[DEMO] %s phase 0: flush cache + invalidate + zero flags", tag)
    try:
        node.setCacheMode(QGraphicsItem.CacheMode.NoCache)
    except Exception:
        pass
    scene = None
    try:
        scene = node.scene()
    except Exception:
        pass
    if scene is not None:
        try:
            scene.invalidate(node.mapRectToScene(node.boundingRect()))
        except Exception:
            pass
    try:
        node.setSelected(False)
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QGraphicsRectItem
        node.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
    except Exception:
        try:
            node.setFlags(QGraphicsItem.GraphicsItemFlags(0))
        except Exception:
            pass

    # ── Manifest: workers (disconnect signals before teardown ripples) ─
    for worker_attr, signal_names in _manifest(node, '_demolition_workers'):
        worker = getattr(node, worker_attr, None)
        if worker is None:
            continue
        for sig in signal_names:
            try:
                getattr(worker, sig).disconnect()
            except (RuntimeError, TypeError, AttributeError):
                pass

    # ── Manifest: timers ──────────────────────────────────────────────
    for timer_attr, slot_name in _manifest(node, '_demolition_timers'):
        timer = getattr(node, timer_attr, None)
        if timer is None:
            continue
        try:
            timer.stop()
        except (RuntimeError, AttributeError):
            pass
        try:
            if slot_name:
                slot = getattr(node, slot_name, None)
                if slot is not None:
                    timer.timeout.disconnect(slot)
                else:
                    timer.timeout.disconnect()
            else:
                timer.timeout.disconnect()
        except (RuntimeError, TypeError):
            pass

    # ── Manifest: animations ──────────────────────────────────────────
    for anim_attr, signal_names in _manifest(node, '_demolition_animations'):
        anim = getattr(node, anim_attr, None)
        if anim is None:
            continue
        try:
            anim.stop()
        except (RuntimeError, AttributeError):
            pass
        for sig in signal_names:
            try:
                getattr(anim, sig).disconnect()
            except (RuntimeError, TypeError, AttributeError):
                pass

    # ── Manifest: media players ───────────────────────────────────────
    for player_attr in _manifest(node, '_demolition_media_players'):
        player = getattr(node, player_attr, None)
        if player is None:
            continue
        try: player.stop()
        except (RuntimeError, AttributeError): pass
        try: player.setVideoOutput(None)
        except (RuntimeError, AttributeError): pass
        try: player.setAudioOutput(None)
        except (RuntimeError, AttributeError): pass
        try: player.deleteLater()
        except (RuntimeError, AttributeError): pass

    # ── Manifest: proxies ─────────────────────────────────────────────
    # Snapshot each proxy's scene rect first — after setWidget(None) the
    # geometry query can still work but the inner widget is gone, and
    # after removeItem the proxy's sceneBoundingRect is meaningless.
    proxy_rects = []
    for proxy_attr in _manifest(node, '_demolition_proxies'):
        proxy = getattr(node, proxy_attr, None)
        if proxy is None:
            continue
        try:
            proxy_rects.append(proxy.sceneBoundingRect())
        except (RuntimeError, AttributeError):
            proxy_rects.append(None)
    for (proxy_attr), snapped in zip(
            _manifest(node, '_demolition_proxies'), proxy_rects):
        proxy = getattr(node, proxy_attr, None)
        if proxy is None:
            continue
        # Canonical teardown order (PrettyEdit recipe, compliance 2026-04-16)
        try:
            inner = proxy.widget()
        except (RuntimeError, AttributeError):
            inner = None
        try: proxy.setWidget(None)
        except (RuntimeError, AttributeError): pass
        if inner is not None:
            try: inner.setParent(None)
            except (RuntimeError, AttributeError): pass
            try: inner.deleteLater()
            except (RuntimeError, AttributeError): pass
        if scene is not None:
            try: scene.removeItem(proxy)
            except (RuntimeError, AttributeError): pass
        try: setattr(node, proxy_attr, None)
        except Exception: pass
        # Invalidate the region the proxy used to paint — belt and braces
        # against stylesheet backing stores leaving rasterised residue
        # (compliance 2026-04-18 PaletteNode artefacts).
        if scene is not None and snapped is not None:
            try: scene.invalidate(snapped)
            except (RuntimeError, AttributeError): pass

    # ── Standard phases from the old BaseNode procedure ──────────────
    # These work against BaseNode-style plumbing (connections list,
    # behaviour instance, button strip, ports).  Each is gated on
    # presence so non-BaseNode roots (StickerNode) flow through too.

    logger.log(5, "[DEMO] %s phase heal: bridge source→target wires", tag)
    if hasattr(node, '_heal_connections'):
        try: node._heal_connections()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} heal raised: {exc}")

    logger.log(5, "[DEMO] %s phase detach: buttons + ports", tag)
    if hasattr(node, '_detach_buttons'):
        try: node._detach_buttons()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} detach buttons raised: {exc}")
    if hasattr(node, '_detach_ports'):
        try: node._detach_ports()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} detach ports raised: {exc}")

    logger.log(5, "[DEMO] %s phase behaviour: disconnect_all", tag)
    behaviour = getattr(node, 'behaviour', None)
    if behaviour is not None:
        try: behaviour.disconnect_all()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} behaviour disconnect raised: {exc}")

    logger.log(5, "[DEMO] %s phase connections: sever wires", tag)
    if hasattr(node, 'connections'):
        try:
            for conn in list(node.connections):
                if hasattr(conn, '_glide_timer'):
                    try: conn._glide_timer.stop()
                    except (RuntimeError, AttributeError): pass
                    try:
                        if hasattr(conn, '_glide_tick'):
                            conn._glide_timer.timeout.disconnect(conn._glide_tick)
                    except (RuntimeError, TypeError): pass
                other = None
                if hasattr(conn, 'start_node') and hasattr(conn, 'end_node'):
                    other = conn.end_node if conn.start_node is node else conn.start_node
                if other is not None and other is not node and hasattr(other, 'connections'):
                    try: other.connections.remove(conn)
                    except ValueError: pass
                try: conn.start_node = None
                except AttributeError: pass
                try: conn.end_node = None
                except AttributeError: pass
                try:
                    if conn.scene():
                        conn.scene().removeItem(conn)
                except (RuntimeError, AttributeError):
                    pass
            node.connections.clear()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} sever connections raised: {exc}")

    # ── Post-hook: bespoke node-specific work after standard sequence ─
    if hasattr(node, '_demolition_post'):
        try:
            node._demolition_post()
        except Exception as exc:
            logger.warning(f"[DEMO] {tag} _demolition_post raised: {exc}")

    logger.log(5, "[DEMO] %s crew leaving — demolition complete", tag)


# ── Internal helpers ─────────────────────────────────────────────────────

def _tag(node) -> str:
    """Build a compact log tag: '<node_type> <uuid_prefix>'."""
    try:
        return f"{node.data.node_type} {node.data.uuid[:8]}"
    except AttributeError:
        return type(node).__name__


def _manifest(node, attr_name: str):
    """Collect a manifest attribute walking the full MRO, so subclass
    declarations EXTEND parent-class declarations rather than shadow
    them.  A BaseNode subclass declaring `_demolition_timers` gets both
    BaseNode's entries AND its own; the crew runs every one.

    Duplicate entries (same attr name in parent and child) are deduped
    in first-seen order — the item is torn down exactly once, and
    parent-class entries stay before child-class entries in the order
    they were declared."""
    seen = set()
    out = []
    for klass in type(node).__mro__:
        items = klass.__dict__.get(attr_name)
        if not items:
            continue
        for item in items:
            # Dedup key: the attr name (first element in every manifest
            # entry shape we use — either a bare string or a tuple whose
            # first element is the attr name).
            key = item if isinstance(item, str) else item[0]
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out
