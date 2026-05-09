#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/palette_satellite.py palette satellite spawning
-Sending a palette node into orbit beside the node that asked for it, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""


def spawn_palette_satellite(scene, parent_node, colors) -> 'PaletteNode | None':
    """Drop a PaletteNode satellite anchored to *parent_node*.

    Returns the spawned PaletteNode, or None when *colors* is empty (no
    palette gets created from an empty list). Placement goes through
    the canonical ``chain_spawn`` — wander_origin + spiral_place — so
    the palette probes for a real free seat instead of being dropped
    at a fixed offset that might land on top of another node.

    The lowest of three layered entry points in this module: callers
    that already have a list of colour dicts in hand call this directly.
    Callers with text or a file path reach for the convenience wrappers
    below.
    """
    if not colors:
        return None
    from utils.placement import chain_spawn, OFFSCREEN_STAGING
    spawned = chain_spawn(
        scene, parent_node, [colors],
        lambda c: scene.add_palette_node(pos=OFFSCREEN_STAGING, colors=c),
    )
    return spawned[0] if spawned else None


def spawn_palette_satellite_from_text(scene, parent_node, text) -> 'PaletteNode | None':
    """Convenience: extract hex colours from *text*, spawn satellite if any found.

    For callers that already have the file's contents in memory (e.g.
    CodeNode after ``load_from_path``) — avoids a redundant disk read.
    """
    from utils.hex_extract import extract_hex_colors
    return spawn_palette_satellite(scene, parent_node, extract_hex_colors(text))


def spawn_palette_satellite_from_file(scene, parent_node, path) -> 'PaletteNode | None':
    """Convenience: read *path*, extract hex colours, spawn satellite if any found.

    For callers operating on a file path with no text in memory yet (e.g.
    drag-drop in ``View.dropEvent``). Read errors are absorbed silently —
    a non-readable file is just "no palette here", not an error condition.
    """
    from utils.hex_extract import extract_hex_colors_from_file
    return spawn_palette_satellite(scene, parent_node, extract_hex_colors_from_file(path))
