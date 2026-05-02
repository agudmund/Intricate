# The Stickers Node

The sticker. A chromeless, frameless PNG dropped directly onto the canvas with its alpha channel composited against whatever sits below — no background fill, no border, no caption, no chrome. If the ImageNode is the camera with the full darkroom behind it, the StickerNode is the peel-and-stick vinyl: you slap it on, you move it around, and the parts you painted transparent in Photoshop stay transparent all the way through.

Conceptually, it's a different node type entirely. BaseNode-derived nodes are structured thinking: a panel, a title, ports, buttons, behaviour. A sticker is none of those things. It is an image on a canvas, and that is the whole contract. StickerNode was the first descendant of `ChromelessRoot` (the parallel root for HUD and ornament nodes — see `Documents/Design/Chromeless Nodes.md`), and the canonical proof that a non-BaseNode root could carry the canvas-citizen contract without dragging in the structural-node apparatus.

## Core Files

| File | Purpose |
|---|---|
| `nodes/StickerNode.py` | The node — chromeless paint, pin logic, resize, shake-delete hooks |
| `data/StickerNodeData.py` | Pure Python dataclass — `source_path`, `image_b64`, pin state |

## How It Works

### Three Ways to Create

1. **Sidebar button** — click the sticker icon in the left sidebar, a blank sticker appears at the canvas centre
2. **Double-click a blank sticker** — opens a file browser and loads the chosen image
3. **Session restore** — `from_dict` rebuilds the data, `__init__` loads from `source_path` if present, falling back to the serialized `image_b64` blob

### The Click-Through Feature

This is the single most important thing about StickerNode and the first invariant that must never regress:

**Stickers have no opaque background.** The node's `paint()` method does not fill the rect — it only draws the pixmap. Everywhere the pixmap's alpha channel is transparent, the canvas behind the sticker remains visible *and interactable*. You can park a sticker on top of a MarkdownNode and drag-select the text underneath through the transparent regions of the image. The opaque pixels are the sticker; the transparent pixels pass through to whatever lives below.

Pixel-accurate. Tested against a pixel-grid image: the hit regions line up to the pixel. This is deliberate behaviour, not a side effect, and it depends on three invariants living together:

1. `paint()` never draws any background fill. No `QBrush`, no `fillRect`, no rounded-rect chrome — only the pixmap (and the empty-state placeholder text when there is no image yet).
2. `setBrush(Qt.NoBrush)` and `setPen(Qt.NoPen)` are set once at construction. `ChromelessRoot` does not own a NodeBehaviour, so there is nothing trying to paint a hover background over the sticker — the previous per-call `setBrush` override that BaseNode-era StickerNode needed is gone.
3. `_fit_to_image()` sizes the node rect tight to the scaled pixmap, so there are no captured transparent margins surrounding the image. The rect *is* the image.

Good use of alpha as a concept: it's already how Photoshop communicates "this pixel is part of the layer, this one isn't". StickerNode just carries that declaration across the filesystem and into the canvas. Intricate respects which parts of the PNG the user painted as tree and which as background.

### Pinning — Viewport-Anchored Stickers

A pinned sticker stays fixed to a point in the **viewport**, not the scene. Pan the canvas, the pinned sticker stays where it is relative to the window. Unpin and it drops back into the scene and moves with everything else.

**Toggle:** double-click a sticker that already has an image loaded, or right-click → "Pin to Viewport" from the context menu.

**Data contract:** the four pin fields live on `ChromelessRootData` (the shared base for the chromeless family) and serialise automatically — `StickerNodeData.to_dict` chains through `super().to_dict()` so they survive every save without per-class bookkeeping.

- `pinned: bool` — whether the sticker is currently in screen-space mode
- `pin_vp_x`, `pin_vp_y` — viewport coordinates (in view-local pixels) the sticker snaps back to on every pan/zoom
- `pin_scale` — canvas zoom captured at pin time, so the visible size stays continuous across the pin/unpin toggle at any zoom level

**Mechanism:** on pin, `ItemIsMovable` is turned off, `ItemIgnoresTransformations` is turned on (so the sticker renders at fixed screen-pixel size regardless of canvas zoom), the current rect is multiplied by the captured zoom (so the visible size is preserved through the IIT toggle), and the viewport position is recorded. On every view transform change (pan, zoom, programmatic transform mutation), the sticker remaps `(pin_vp_x, pin_vp_y)` back through `view.mapToScene(...)` and `setPos()`es to the resolved scene position. The result is that the sticker appears locked in the viewport at a fixed screen size, regardless of how the user pans or zooms the canvas.

**Wiring:** the view declares its transform changes via a `viewTransformed` signal — pinned stickers subscribe to that. An NFL player's spatial awareness: the sticker is not trying to predict the canvas, it is listening for the canvas to announce itself, and adjusting its position the instant it hears the announcement. Scrollbar `valueChanged` subscriptions are kept as a secondary channel for the rare case where the scene grows past the viewport and the scrollbars do move.

**Inheritance:** all of this — IIT toggle, viewport tracking, the two-path `_activate_pin` (user-initiated vs session-restore), the `pin_scale` capture/divide — lives on `ChromelessRoot` and is shared verbatim with JoyStatsNode and ValueNode. See `Documents/Design/Chromeless Nodes.md` for the full pin-contract design.

### Resize

Drag the bottom-right corner to resize the sticker. The pixmap inside is aspect-fit into the new rect — `QPainter` centres the scaled image, with whatever transparent margin falls around it. The rect grows or shrinks; the image stays proportional.

### Media Cache Integration

Stickers ride the same content-addressed media cache as ImageNode and VideoNode — full retention, full dedup, full drift detection. The framework itself is documented separately in `Documents/Design/Media Cache.md`; what follows is the sticker-specific view of it.

**Load hierarchy on construction:**

1. **`cache_key` present** → `load_cached(cache_key)` pulls the pixmap from the content-addressed cache. If `source_path` also exists and resolves on disk, a fingerprint (size + mtime) check runs synchronously. On fingerprint mismatch, a streaming SHA-256 verifies whether the source has actually drifted; a real hash mismatch queues an AboutNode next to the sticker with `source drifted — cache no longer matches`.
2. **`source_path` only** → the raw bytes get read once, cached via `cache_source_bytes(raw, ext)`, and decoded for display in the same pass. The returned key, plus fingerprint (`source_size`, `source_mtime`), goes into the dataclass so the next restore takes the fast cache-first path.
3. **`image_b64` only** → legacy pre-cache session. The base64 is decoded for display as-is; on next save the pixmap is migrated into the cache via `to_dict` → `cache_pixmap`, and the b64 field stops being written.

**Save path:** `to_dict` ensures a `cache_key` exists before serializing. If the sticker was pasted or generated (no source file, no cache entry), `cache_pixmap(self._pixmap)` PNG-encodes the pixmap into the cache and stamps the returned key. `image_b64` is only written as a legacy tail when there is *neither* a cache_key nor a source_path — practically never for new stickers.

**GC participation:** `graphics/Scene.py`'s `gc_cache` sweep at session save time whitelists `_CACHED_TYPES = {"image", "video", "sticker"}`. Every live sticker's cache_key contributes to `live_keys`; any cache file not referenced by any live node is removed. Delete a sticker, save the session — its cached bytes are reclaimed on that same save, unless another node (or another sticker) still refers to the same hash.

**Dedup is free:** ten copies of the same sticker PNG on canvas share one file in the cache. Drag the same PNG into a sticker and an image node and they share one cached file too. The sticker class of node-type does not have a privileged dedup namespace — it deduplicates against the entire media cache, across every node type.

**Drift example.** A sticker is created pointing at `~/Downloads/cat.png`. The session is saved. The user later re-exports `cat.png` from Photoshop with a new tEXt chunk embedded. On the next session load, the sticker's `cache_key` still resolves against the old pre-export bytes, but the source fingerprint now differs. A streaming SHA confirms the content has genuinely changed. An AboutNode appears next to the sticker: *sticker source drifted — cache no longer matches*. The user decides — refresh the cache from the sidebar menu to pull in the new version, or leave the sticker pinned to the original bytes.

### Paint Pipeline

`paint()`:

1. `setRenderHint(Antialiasing)` — for smooth edges on scaled pixmaps
2. `setRenderHint(SmoothPixmapTransform)` — bilinear scaling when the sticker is rendered at a different size than the source
3. Hand off to `paint_content(painter)` — no chrome, no fill

`paint_content()`:

1. If there's no pixmap yet, draw the placeholder text "double-click to load sticker" in `Theme.textPrimary`
2. Otherwise aspect-fit the pixmap into the current rect via `pixmap.size().scaled(rect_size, KeepAspectRatio)`
3. `drawPixmap(dest_rect, self._pixmap)` — that's the whole paint

No borders, no shadows, no rounded corners, no selection glow. The visual appearance is identical whether the sticker is selected or not. That's the feature.

### Cursor Behaviour

`mousePressEvent` hides the cursor (`Qt.BlankCursor`) while dragging the sticker; `mouseReleaseEvent` restores it. A sticker being dragged should look like it's peeling from your fingertip, not chasing the arrow — the cursor disappearing reinforces the physical metaphor.

### Z-Depth

`_Z_FLOOR = 100.0`. Stickers float above regular nodes by default. The `setZValue` override clamps any attempt to push them below the floor. Same design as `ValueNode`: things the user treats as ornaments or annotations stay above the structural content.

### Shake-to-Delete

Inherited from `ChromelessRoot`'s shake gesture (composition over `ShakeDetector` — same one BaseNode uses). Shake a sticker hard and it dissolves with a particle burst like any other node. StickerNode overrides `_on_shake_triggered` to pick between `sprinkle` and `orbital_burst` particle effects based on the sticker's alpha coverage — large opaque stickers get the orbital burst, mostly-transparent ones get sprinkle. The `_quiet_for_shake()` synchronous-quiet hook from the root disconnects viewport tracking before the deferred `removeItem` window opens, closing the race window where a transform tick could land on a node about to vanish (see `Documents/Compliance/Node Cleanup Compliance.md`, 2026-04-18 entry).

## Data Class

`StickerNodeData` extends `ChromelessRootData` (which extends `NodeData`). The pin fields are inherited; `to_dict` chains through `super().to_dict()` so they always serialise without per-class bookkeeping.

Sticker-specific fields:

- `cache_key: str` — SHA-256 key into the shared media cache (`<sha256>.<ext>`). Primary persistence channel.
- `source_path: str` — absolute path to the source PNG on disk. Provenance anchor; drives the drift check on restore.
- `source_size: int`, `source_mtime: float` — cheap drift fingerprint recorded at last cache write. A clean fingerprint skips the streaming SHA on restore.
- `image_b64: str` — legacy base64-encoded PNG. Always written empty for new stickers; retained in `from_dict` so pre-cache sessions still load.

Inherited from `ChromelessRootData`:

- `pinned: bool` — current pin state.
- `pin_vp_x: float`, `pin_vp_y: float` — viewport coordinates for the pin anchor.
- `pin_scale: float` — canvas zoom captured at pin time, used as a layout-scale multiplier across the IIT toggle.

Default size: 200 × 200, auto-fit to the image on first load (see `_fit_to_image`).

## Lifecycle

### Creation

`Scene.add_sticker_node(pos)` → `StickerNode(StickerNodeData())`. The sticker appears blank with the "double-click to load" placeholder.

### Session restore

`StickerNodeData.from_dict(d)` → `StickerNode(data)`. `__init__` prefers `source_path` when present (live load from disk), falls back to `image_b64` (embedded blob). If `data.pinned` was True at save time, a `QTimer.singleShot(0, self._activate_pin)` re-establishes the pin after the view is ready.

### Removal

`_demolition_pre()`:

1. Calls `super()._demolition_pre()` for `ChromelessRoot`'s viewport-tracking disconnect
2. Nulls `_pixmap` to release the image buffer

`_quiet_for_shake()`:

1. Calls `super()._quiet_for_shake()` from `ChromelessRoot` to synchronously sever the viewport signals before a shake-delete defers `removeItem`. Without this, a scrollbar or `viewTransformed` tick landing mid-teardown collided with Qt's destructor and fastfailed the process (Event Viewer `0xc0000409`, ucrtbase.dll). Documented in `Documents/Compliance/Node Cleanup Compliance.md`.

### Serialization

`to_dict()`:

1. `sync_data()` folds current geometry into the dataclass
2. If `source_path` is empty and a pixmap exists (vision-generated, drag-drop without a file path), encode the pixmap as base64 PNG into `image_b64`
3. Return `data.to_dict()` — which chains through `ChromelessRootData.to_dict` so the pin fields ride along automatically

The session JSON carries either `cache_key` + `source_path` (preferred — bytes live in the content-addressed cache, source file lives on disk) or `image_b64` (legacy fallback — pixmap round-tripped through PNG encoder).

## Technical Notes

- Stickers do not have ports and cannot be wired. The `connections` list provided by `ChromelessRoot` stays empty for the lifetime of the node. Any feature that iterates scene nodes for connection data already skips stickers because their `connections` is duck-typed-empty.
- The `_Z_FLOOR = 100.0` floor matches ValueNode. Both are "things the user puts on top of structural work".
- Alpha-channel hit-testing is currently rect-based at the `shape()` level, but the visual click-through (text selection passing through transparent regions) works because `paint()` leaves those pixels unpainted — items below stay visible and their event dispatch still fires when the click lands in a region the sticker didn't claim with a bounding interaction. Preserve this by never adding a background fill.
- `_fit_to_image()` re-fits only when the rect is still at the 200×200 default — resizing to exactly 200×200 and then loading a new image will trigger a refit. A resize-by-user-flag would make this crisper; today the corner case is rare enough to leave alone.
- StickerNode opts out of `ChromelessRoot._UNPINNED_RESIZE_ENABLED` (it stays `False` on the class) because the sticker has its own bespoke resize gesture with aspect-ratio preservation and cursor-hide. Other chromeless descendants (JoyStatsNode, ValueNode) opt in and get the generic corner grip for free.
- StickerNode is the reference implementation of the chromeless contract — the first descendant of `ChromelessRoot` and the model future raw-image-style nodes (postcards, patches, cut-outs) will inherit from. See `Documents/Design/Chromeless Nodes.md` for the framework-level documentation.
