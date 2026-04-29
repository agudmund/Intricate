# The Value Node

A chromeless node that displays one frame of an image sequence with an invisible scrubber running along its base. Drag the scrubber and the frame swaps — a live value readout rendered as a picture, with none of the usual node chrome getting in the way. Think of it as a dial that happens to be painted rather than numeric: whatever visual story the frame sequence tells (a bar filling, a gauge sweeping, a mood shifting) is what the node communicates.

Where StickerNode is a peel-and-stick PNG (static, non-interactive, the parts you painted transparent in Photoshop stay transparent), ValueNode is the same chromeless contract with a slider bolted on. It is the second chromeless node in the tree, and the natural next inheritance test once StickerNode's detachment from BaseNode lands.

## Core Files

| File | Purpose |
|---|---|
| `nodes/ValueNode.py` | The node — transparent paint, natural-key frame scan, slider proxy, calibrated crop |
| `data/ValueNodeData.py` | Pure Python dataclass — `current_frame` persistence |
| `Images/Value/` | The frame library. Any `.png/.jpg/.jpeg/.bmp/.gif/.webp` in this folder becomes a frame |

## How It Works

### The Frame Library

`./Images/Value/` is scanned at construction. Every image file is sorted by `_natural_key` — a numeric split so `bar10.png` lands after `bar9.png` rather than after `bar1.png`. The default ship set is `bar00.png` through `bar10.png` (11 frames), a progress-bar fill animation rendered as individual PNGs with transparent padding.

Drop new files into the folder and they are picked up the next time a ValueNode is constructed. No registry, no manifest, no rebuild. The folder *is* the declaration.

### The Slider

A PrettySlider lives inside a `QGraphicsProxyWidget` pinned to the bottom strip of the node. It has:

- **Invisible groove** — zero height, transparent background
- **Invisible handle** — 28×28 hit area, also transparent
- **No pages** — add/sub page sections are both transparent

You cannot see the slider. You can interact with it. Drag anywhere along the bottom of the node and the frame scrubs; the visible result is the image swapping, not a handle moving. The slider is pure input surface — the pixmap underneath is the feedback channel.

Range is `(0, len(frames) - 1)`. `valueChanged → _seek` loads the pixmap for that index and triggers a repaint.

### Transparent Fill

ValueNode carries the same chromeless contract as StickerNode, implemented through three deliberate invariants:

1. **`setBrush(Qt.NoBrush)` is enforced on every call.** NodeBehaviour's hover glow tries to set a background colour every frame; the `setBrush` override intercepts it and forces NoBrush. Without this, the chromeless transparency would blink with the pulse animation.
2. **`setCacheMode(NoCache)`.** Qt's `DeviceCoordinateCache` renders through an opaque pixmap intermediate — with the cache enabled, NoBrush has no visible effect because the cache fills the backing store with black. Disabling the cache is what lets the transparent paint actually reach the scene.
3. **The proxy widget itself is translucent.** `WA_TranslucentBackground` + `setAutoFillBackground(False)` on the inner slider, so the proxy doesn't paint its own opaque rectangle over the transparent node body.

Remove any one of these and the node's transparency breaks. They are all required, and they are all load-bearing.

### Calibrated Crop

Source PNGs in `./Images/Value/` carry transparent padding — the bar graphic does not fill the file edge-to-edge. If ValueNode used the raw pixmap dimensions, the node border (and hit area) would sit out beyond the visible content with a transparent gutter in between.

The `_CAL_*` class constants are the baseline correction:

```python
_CAL_LEFT   = 0
_CAL_RIGHT  = 15
_CAL_TOP    = 0
_CAL_BOTTOM = 7
```

These trim the baked-in padding so the node's clipping path and slider geometry align with the visible pixels, not the file bounds.

Two more calibration constants live alongside the crop:

```python
_CAL_PORT_Y = -12   # port Y offset from rect center
_CAL_PORT_X =  10   # port X offset from the base -ox left-edge
_CAL_PORT_X_OFFSET = 0.0   # additional port nudge — pinned in code
_CAL_PORT_Y_OFFSET = 0.0
```

These anchor the single input port to the tip of the bar graphic rather than the rect centre. The pre-ChromelessRoot `[node.value]` TOML section that used to layer crop and port offsets on top of these constants has been retired — the framework owns those concerns now, and any further nudge lives directly on the class as a small named constant rather than as a runtime-tunable setting.

### Ports

One W input, one E output. Both are created and positioned, then `.hide()`'d. The node is connection-aware but does not advertise connection affordances visually — the ports are a data contract, not a UI surface. `closest_input_port` and `closest_output_port` return their single respective port unconditionally so wire routing still works when another node reaches toward a ValueNode.

The port Y is anchored to the image content via `_CAL_PORT_Y` rather than rect centre, so as the user resizes the node the port tip stays visually pinned to the bar graphic's terminus rather than drifting with the rect.

### Z-Depth

`_Z_FLOOR = 100.0`. ValueNode floats above regular nodes by default. `setZValue` clamps any attempt to push it below the floor. Same design as StickerNode: things the user treats as dials, gauges, or annotations stay above the structural content.

### Resize

Dragging the bottom-right corner resizes the rect. Both port placement and slider proxy geometry re-anchor on `setRect` — BaseNode's default `_place_ports` gates on `output_ports` existing, and ValueNode's input port needs re-anchoring independently, so `setRect` calls `_place_ports` directly instead of relying on the BaseNode path.

The pixmap inside is aspect-fit to the new `_image_rect` (full width, full height minus the slider band) via `KeepAspectRatioByExpanding` — the image fills the node, centred, cropped rather than letterboxed. The bar can be made as tall or as short as the user wants; the frame content stretches to fill without visible dead space.

### No Button Strip

`_build_buttons` is a no-op. Deletion is via shake. There are no per-node actions — the only interaction surfaces are the slider (scrub) and the corner handle (resize). Shake-to-delete inherits from BaseNode's shake-detect logic and produces a particle burst like any other node.

### Paint Pipeline

`paint()` — sets antialiasing and hands off to `paint_content`. No chrome, no fill, no border, no selection glow.

`paint_content()`:

1. If crop settings changed since last paint, re-anchor the slider proxy. This is the sync point where TOML-edited crop values flow through to the visible slider position without a full reconstruction.
2. If there is no pixmap (empty folder, missing file, first frame not yet seeked), return. The node paints as pure transparency.
3. Otherwise clip to the cropped rect (rounded corners), aspect-fit the pixmap into `_image_rect`, and `drawPixmap` into the centred destination.

`shape()` returns the cropped rounded rect — hit testing matches the visible bar, not the raw rect. `boundingRect()` is the cropped rect expanded by `Theme.nodeShadowMargin` on all sides, so the shadow (if any) is not clipped away on repaint.

## Data Class

`ValueNodeData` extends `NodeData` with a single stateful field:

- `current_frame: int` — index into the sorted frame list, persisted across sessions

Defaults: 130×80, `current_frame = 0`.

On restore, `__init__` clamps `current_frame` to the current frame list length before seeking — if the folder shrinks between sessions, the node snaps to a valid index rather than crashing.

## Lifecycle

### Creation

`Scene.add_value_node(pos)` → `ValueNode(ValueNodeData())`. The node appears at frame 0.

### Session restore

`ValueNodeData.from_dict(d)` → `ValueNode(data)`. `__init__` scans the frame folder, clamps the persisted `current_frame` to the current length, and seeks without triggering `valueChanged` — the slider is set with signals blocked, then `_seek` is called directly to load the pixmap.

### Removal

`_demolition_pre` disconnects the slider's `valueChanged → _seek` connection before the proxy teardown crew tears the inner widget down. Without this, the slider's `setParent(None) + deleteLater()` can fire during a pending `valueChanged` and collide with half-disposed state.

`_demolition_post` nulls `_slider` so any late reference resolves cleanly. `_demolition_proxies = ['_slider_proxy']` tells the shared teardown crew which QGraphicsProxyWidget fields to walk.

### Serialization

`to_dict()` calls `sync_data()` to fold current geometry into the dataclass, then returns `data.to_dict()`. The frame library itself is not serialized — only the index into it. Sessions stay tiny.

## Detachment Plan

ValueNode inherits from BaseNode and overrides enough to suppress the chrome. It pays the same inheritance tax as StickerNode pre-detachment: every feature added to BaseNode must be checked against "does ValueNode want this, and if not, what's the silencing pattern?" — a permanent cost for a node that conceptually shares very little with BaseNode beyond "lives on the canvas and persists".

Once StickerNode's detachment refactor settles (user-tested, no regressions), ValueNode is the natural second inheritance test of the new chromeless root. It validates that the root was designed with future raw-sibling types in mind — not just built to solve the sticker-specific case. StickerNode is the pinned, non-interactive overlay; ValueNode is the chromeless interactive sibling. Between them, the root's extension surface gets exercised in both directions.

Until that refactor lands, the `setBrush`, `setCacheMode`, `shape`, `boundingRect`, `paint`, and `_build_buttons` overrides all serve as the silencing layer that keeps BaseNode features from leaking into the raw visual surface.

## Technical Notes

- The 11-frame default set (`bar00.png` through `bar10.png`) is a progress-bar fill animation, 0% through 100% in 10% steps. Replacing the folder with a different sequence (mood meter, volume gauge, weather icon run) changes the node's semantic meaning without any code change. The node is agnostic to what the frames represent.
- `_natural_key` matters as soon as you have more than 10 frames. Without it, `bar10` sorts before `bar2`, and scrubbing produces an out-of-order animation. The sort is applied once at scan time and the result is cached in `self._frames`.
- `_last_crop` is the change-detect for crop settings. TOML edits flow through `Theme` live-reload → next paint → `paint_content` sees a different tuple → slider proxy re-anchors. No explicit reload signal is wired; the paint pass is the observation point.
- The slider's `handle_size=28` is the PrettySlider constructor parameter, not a stylesheet value. The stylesheet then sets a matching `width/height: 28px` and a negative vertical margin (`-14px`) to centre the hit area on the zero-height groove. All three values must agree or the handle drifts above or below the click zone.
- `NodeBehaviour.pulse_anim` still runs on ValueNode (scales it subtly on hover). The visual effect is invisible because the pixmap aspect-fits to whatever rect size is current, but the timer tax remains. The detachment refactor will remove it.
- The input port's hidden state is `Port.hide()`, not removal — the port object still exists, still participates in connection resolution, and still anchors wires. Only its visual representation is suppressed.
