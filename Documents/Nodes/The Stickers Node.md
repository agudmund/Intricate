# The Stickers Node

The sticker. A chromeless, frameless PNG dropped directly onto the canvas with its alpha channel composited against whatever sits below — no background fill, no border, no caption, no chrome. If the ImageNode is the camera with the full darkroom behind it, the StickerNode is the peel-and-stick vinyl: you slap it on, you move it around, and the parts you painted transparent in Photoshop stay transparent all the way through.

Conceptually, it's a different node type entirely. BaseNode-derived nodes are structured thinking: a panel, a title, ports, buttons, behaviour. A sticker is none of those things. It is an image on a canvas, and that is the whole contract.

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

1. `paint()` and `paint_content()` never draw any background fill. No `QBrush`, no `fillRect`, no rounded-rect chrome.
2. `setBrush(Qt.NoBrush)` is enforced on every call. `NodeBehaviour.bg_anim` tries to set a hover background colour every frame; the override intercepts it. When the NodeBehaviour dependency eventually goes away (see the "Detachment plan" section below) this override can go with it.
3. `_fit_to_image()` sizes the node rect tight to the scaled pixmap, so there are no captured transparent margins surrounding the image. The rect *is* the image.

Good use of alpha as a concept: it's already how Photoshop communicates "this pixel is part of the layer, this one isn't". StickerNode just carries that declaration across the filesystem and into the canvas. Intricate respects which parts of the PNG the user painted as tree and which as background.

### Pinning — Viewport-Anchored Stickers

A pinned sticker stays fixed to a point in the **viewport**, not the scene. Pan the canvas, the pinned sticker stays where it is relative to the window. Unpin and it drops back into the scene and moves with everything else.

**Toggle:** double-click a sticker that already has an image loaded.

**Data contract:**
- `pinned: bool` — whether the sticker is currently in screen-space mode
- `pin_vp_x`, `pin_vp_y` — the viewport coordinates (in view pixels) where the sticker should stay

**Mechanism:** on pin, `ItemIsMovable` is turned off and the current viewport position is recorded. On every view transform change (pan, zoom, or any programmatic transform update), the sticker remaps `(pin_vp_x, pin_vp_y)` back through `view.mapToScene(...)` and `setPos()`es to the resolved scene position. The result is that the sticker appears locked in the viewport while the scene continues to translate beneath it.

**Wiring:** the view declares its transform changes via a `viewTransformed` signal — pinned stickers subscribe to that. An NFL player's spatial awareness: the sticker is not trying to predict the canvas, it is listening for the canvas to announce itself, and adjusting its position the instant it hears the announcement. Scrollbar `valueChanged` subscriptions are kept as a secondary channel for the rare case where the scene grows past the viewport and the scrollbars do move.

**Zoom behaviour (first pass):** scene size stays fixed, so the sticker scales visually with the zoom — it grows larger on zoom-in. True screen-space size lock (counter-scaling by `1/view.transform().m11()`) is a separate feature pass; the current priority is the x/y pin.

### Resize

Drag the bottom-right corner to resize the sticker. The pixmap inside is aspect-fit into the new rect — `QPainter` centres the scaled image, with whatever transparent margin falls around it. The rect grows or shrinks; the image stays proportional.

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

Inherited from BaseNode's shake-detect logic. Shake a sticker hard and it dissolves with a particle burst like any other node. The `_quiet_for_shake()` override fires synchronously at shake-start to disconnect pin-tracking signals before the deferred `removeItem` window opens (see `Documents/Compliance/Node Cleanup Compliance.md`, 2026-04-18 entry).

## Data Class

`StickerNodeData` extends `NodeData` with:

- `image_b64: str` — base64-encoded PNG fallback for sessions where the original source path no longer resolves. Written on `to_dict` only when `source_path` is empty.
- `source_path: str` — absolute path to the source PNG on disk. Primary load route.
- `pinned: bool` — current pin state
- `pin_vp_x: float`, `pin_vp_y: float` — viewport coordinates for the pin anchor

Default size: 200 × 200, auto-fit to the image on first load (see `_fit_to_image`).

## Lifecycle

### Creation

`Scene.add_sticker_node(pos)` → `StickerNode(StickerNodeData())`. The sticker appears blank with the "double-click to load" placeholder.

### Session restore

`StickerNodeData.from_dict(d)` → `StickerNode(data)`. `__init__` prefers `source_path` when present (live load from disk), falls back to `image_b64` (embedded blob). If `data.pinned` was True at save time, a `QTimer.singleShot(0, self._activate_pin)` re-establishes the pin after the view is ready.

### Removal

`_prepare_for_removal()`:

1. Disconnects viewport tracking signals (horizontal + vertical scrollbar, plus `viewTransformed` once the signal is wired)
2. Nulls `_pixmap` to release the image buffer
3. Calls `super()._prepare_for_removal()` to complete BaseNode teardown

`_quiet_for_shake()`:

1. Synchronously severs the viewport signals before a shake-delete defers `removeItem`. Without this, a scrollbar or `viewTransformed` tick landing mid-teardown collided with Qt's destructor and fastfailed the process (Event Viewer `0xc0000409`, ucrtbase.dll). Documented in `Documents/Compliance/Node Cleanup Compliance.md`.

### Serialization

`to_dict()`:

1. `sync_data()` folds current geometry into the dataclass
2. If `source_path` is empty and a pixmap exists (vision-generated, drag-drop without a file path), encode the pixmap as base64 PNG into `image_b64`
3. Return `data.to_dict()`

The session JSON carries either `source_path` (preferred — file lives on disk, byte-exact) or `image_b64` (fallback — pixmap round-tripped through PNG encoder).

## Detachment Plan

Historically StickerNode inherits from BaseNode and overrides just enough to suppress the chrome. This creates a small paradox: every feature added to BaseNode must be checked against "does the sticker want this, and if not, what's the silencing pattern?" — a permanent tax for a node that conceptually shares nothing with BaseNode except "lives on the canvas". The `setBrush` guard and the NodeBehaviour cost both exist only because of the inheritance.

The intended end state is StickerNode inheriting directly from a sibling root of BaseNode (likely `QGraphicsRectItem` or `QGraphicsPixmapItem`), with a minimal session/shake contract reimplemented locally. That refactor is planned; until it lands, the `setBrush`, `shape`, `boundingRect`, `paint`, and `_build_buttons` overrides all serve as the silencing layer that keeps BaseNode features from leaking into the raw visual surface.

When the detach refactor does land, StickerNode becomes the reference implementation for future raw-image-style nodes (postcards, patches, cut-outs) that want to share the chromeless-alpha-PNG pattern without inheriting BaseNode's full apparatus.

## Technical Notes

- Stickers do not have ports and cannot be wired. `_create_ports()` is overridden to empty lists; `_build_buttons()` is a no-op. Any feature that iterates scene nodes for connection data should already skip stickers because their `connections` list stays empty.
- The `_Z_FLOOR = 100.0` floor matches ValueNode. Both are "things the user puts on top of structural work".
- Alpha-channel hit-testing is currently rect-based at the `shape()` level, but the visual click-through (text selection passing through transparent regions) works because `paint()` leaves those pixels unpainted — items below stay visible and their event dispatch still fires when the click lands in a region the sticker didn't claim with a bounding interaction. Preserve this by never adding a background fill.
- `_fit_to_image()` re-fits only when the rect is still at the 200×200 default — resizing to exactly 200×200 and then loading a new image will trigger a refit. A resize-by-user-flag would make this crisper; today the corner case is rare enough to leave alone.
- `NodeBehaviour.pulse_anim` still runs on stickers (scales them subtly on hover). The effect is invisible because the sticker paints itself identically at any scale within the pulse range, but the timer tax remains. The detachment refactor will remove it.
