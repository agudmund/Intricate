# The Image Node

The image display node. Drag-and-drop a file from Explorer, browse via double-click, or paste a pixmap — ImageNode handles all three and puts the result on the canvas. Behind the simple rectangle lives a full proprietary image pipeline: content-addressed byte-preserving cache, LOD-aware scaled rendering, EXIF-honouring decode, Vision API integration, PNG metadata stamping, and passive drift detection against the source on disk.

It is not a cat photo widget. It is a cat photo widget backed by infrastructure that respects every embedded stamp, ICC profile, Adobe footprint, and custom tEXt chunk the file ever acquired — because the moment you start moving images between tools and versions of tools and decades of tools, that metadata is the provenance.

## Core Files

| File | Purpose |
|---|---|
| `nodes/ImageNode.py` | The node — paint, buttons, loading, stamping, Vision integration |
| `data/ImageNodeData.py` | Pure Python dataclass — `cache_key`, `source_path`, `caption`, flags |
| `utils/media_cache.py` | SHA-256 content-addressed byte-preserving cache (shared with VideoNode) |
| `utils/vision.py` | VisionWorker — async Claude API call for image identification |
| `utils/persistence/png_stamp.py` | PNG tEXt stamp read/write helpers |

## How It Works

### Three Ways to Create

1. **Drag-and-drop from Explorer** — `IntricateView.dropEvent` creates an empty ImageNode and calls `load_from_path`
2. **Double-click an empty image area** — opens a file browser starting at the last used directory (`[node.image.last_dir]` in settings)
3. **Session restore** — `from_dict` rebuilds the data, `__init__` fires a worker to load from cache, source, or legacy base64 blob

All three converge on the same async pipeline.

### Async Loading Pipeline

File I/O, SHA hashing, and image decode run on daemon threads so the canvas never stalls. Two threads exist:

- **Drop worker** (`load_from_path` inner `_worker`) — reads raw bytes from a freshly specified path, caches them, decodes for display
- **Restore worker** (`_image_load_worker`) — runs at node construction time, tries cache → source → legacy base64 in order

Both write to `_pending_pixmap` / `_pending_cache_key`. A main-thread `QTimer` at 100ms polls `_check_image_delivery()`, which atomically swaps the pending values into `_pixmap` / `data.cache_key`, nulls the scaled cache, and triggers a repaint. The `_pending_drift` field carries the drift-warning message (see below).

### The Cache — Byte-Preserving, Content-Addressed

The v0.2 cache (`utils/media_cache.py`) stores source file bytes verbatim:

```
cache_dir/
├── 3a7f…b2c1.jpg    ← raw JPEG bytes from user's drop
├── 8e04…1fdd.png    ← PNG with full Adobe XMP block intact
└── c9a2…7733.webp   ← original WebP, no round-trip loss
```

- **Keys are dotted**: `<sha256>.<ext>` — self-describing filenames. No extension registry needed; `load_cached` opens `cache_dir / key` directly.
- **Writes are verbatim**: `cache_source_bytes(raw, ext)` hashes the bytes, writes them as-is. No QPixmap round-trip, no PNG re-encode.
- **Deduplication is free**: two nodes dropping the same file produce the same hash and the same filename — second write is skipped.
- **Legacy compatibility**: bare-hash keys (v0.1 format) still resolve via a fallback that tries `<key>.png`. Old sessions load without migration.

What the cache preserves (because the file on disk IS the source bytes):

- EXIF — camera data, GPS, capture time, orientation flags
- XMP — Adobe sidecar data, ratings, color labels, edit history
- ICC profiles — embedded colour spaces
- tEXt chunks — Intricate `read_png_vision_stamp` captions, other tools' custom metadata
- Format — JPEG stays JPEG, PNG stays PNG, WebP stays WebP

Non-file origins (paste, vision-generated) still exist. Those fall back to `cache_pixmap()`, which PNG-encodes the in-memory pixmap and caches it as `<hash>.png`.

### Cache Refresh

Right-click the empty space on the titlebar → **Refresh Image Cache**. The action:

1. `send2trash`es every file in the project cache directory (recycle bin, not hard delete)
2. Walks every live `ImageNode`:
   - If `source_path` exists on disk: hashes it, compares against the pre-refresh `cache_key` to count drift, then re-loads from source (which re-caches)
   - If no source but an in-memory pixmap exists: re-caches via `cache_pixmap`
3. Reports totals in the info popup: `Image cache refreshed — N image(s) (M had drifted)`

A 70-image session completes refresh in under a second.

### Passive Drift Detection

When a session restores and a cache hit succeeds, the worker also checks: does `source_path` still exist, and does its content hash still match the cached key's hash portion? If they disagree, the worker sets `_pending_drift` with a description. The main-thread delivery handler spawns an AboutNode on the canvas: `source drifted — cache no longer matches` plus the filename.

This catches three cases:

- **External stamp** — Adobe or another tool wrote its own metadata chunks
- **Pixel edit** — source was resized, retouched, re-saved in another app
- **File replacement** — a different image was copied over the source path

The cache is left intact. The user decides: re-cache via the refresh menu, or investigate why the source changed.

Cost is one streaming SHA-256 per node on restore when source is extant. ~20ms per 6MB file, deferred to the background worker, invisible at session-open time.

### Rendering Pipeline

`paint_content(painter)` runs hot — it paints every time the node needs redraw. The work is decoupled into two tiers:

**Source pixmap** (`self._pixmap`) — full resolution, decoded once on load, held in memory. Never painted directly.

**Scaled cache** (`self._scaled_cache`) — the bitmap actually drawn. Keyed on `(image_rect_width × LOD, image_rect_height × LOD)` where LOD is the view's zoom factor read from `painter.worldTransform().m11()`, quantized to 0.5 steps so continuous zooming doesn't thrash. Clamped at source pixmap size — scaling beyond native resolution returns the source itself.

On each paint:

1. Read the current LOD from the painter's transform
2. Compute the target pixel size; if it doesn't match `_scaled_cache_size`, regenerate via `QPixmap.scaled(..., Qt.SmoothTransformation)`
3. Aspect-fit a draw rect into `image_rect` (regardless of scaled cache's pixel size — at extreme zoom, the capped cache gets painter-upscaled rather than shrinking into the centre)
4. Clip to a rounded rectangle so the image respects the node's corner radius
5. Draw the scaled bitmap with `SmoothPixmapTransform` hint enabled
6. Paint the border (ivory ring or default bevel depending on `show_border` flag)

The LOD cache means pan and hover repaints cost ~1.3ms per frame even for 6000px sources. A rescale (only on zoom-step crossings) costs ~10ms at that size.

### EXIF Orientation

`_decode_with_orientation(raw)` is the decode used everywhere. It wraps the raw bytes in a `QBuffer`, feeds a `QImageReader` with `setAutoTransform(True)`, and returns the oriented `QImage`. JPEGs with rotation flags (EXIF orientation 3/6/8) display the correct way up on first paint — no manual rotation path.

### Vision Integration

The node has three pathways into the Claude Vision API:

1. **Eye-icon button** → `_vision_rename()` → spawns a `VisionWorker` that uploads the image with the prompt `"Describe this image in 5 words or fewer. Return only the description, no punctuation."`
2. **Fast path for stamped PNGs** → `read_png_vision_stamp(path)` short-circuits the API call. If the file carries an `Intricate: <caption>` tEXt chunk from a prior session, the stamp is returned immediately, no network round-trip.
3. **Wired ClaudeNode connection** — `_trigger_vision()` routes the image's base64 payload to a connected `ClaudeNode` for a custom prompt flow.

On success, `_on_vision_result(text)` sets the caption and spawns a connected `AboutNode` with the label. On failure, `_on_vision_failed(error)` spawns an AboutNode containing the raw API error — the user always sees the failure reason on canvas, never hidden in a log.

The worker's `finished` and `failed` signals are severed in `_prepare_for_removal()` before the node leaves the scene. Without this, a late-finishing Vision call would invoke `_spawn_caption_node` on a destroyed Qt object and hard-crash.

### PNG Stamping

The 💎 button (`_stamp_source_file`) writes the connected AboutNode's caption into the source PNG's tEXt metadata as `Intricate: <caption>`. Requires:

- A `source_path` that exists on disk
- Exactly one connected AboutNode (zero or more than one is rejected with a status AboutNode)
- The file is actually a PNG at the binary level (magic number `\x89PNG\r\n\x1a\n` is checked explicitly — a `.png` extension on a JPEG is caught and reported)

After the write, the stamp is read back and verified. If verification passes, the node re-reads the now-stamped source bytes, re-hashes, re-caches via `cache_source_bytes`, and updates `data.cache_key`. The cache always mirrors the stamped version of the source. The old pre-stamp cache entry becomes an orphan and gets swept up by `gc_cache` on the next session save.

The 🔍 button (`_inspect_stamp`) reads the stamp back and displays it in an AboutNode. Useful for verifying what a file was tagged with before Intricate ever touched it.

### Format Conversion

The 🔄 button (`_convert_to_png`) takes the source file, opens it with Pillow, saves it as PNG next to the original, and re-loads the node pointing at the new `.png`. Useful for making a JPEG stamp-ready. The conversion is PIL-based so it handles formats Qt sometimes stumbles on (certain CMYK JPEGs, layered TIFFs).

Supported priority formats in Intricate: **PNG, TIFF, EXR**. WebP is anticipated as an ingestion format for files pulled from the modern internet. JPEG is cached verbatim on ingestion but typically converted to PNG before stamping.

### Buttons

Live on the button shelf along the top strip. Collapse with double-click on the top strip, expand with the same.

| Button | Type | Action |
|---|---|---|
| 👁 vision-rename | sidebar icon | Ask Claude what the image is, set caption |
| 💎 stamp | emoji | Write connected AboutNode's label into source PNG metadata |
| 🔍 inspect | emoji | Read PNG tEXt stamp, spawn AboutNode with contents |
| ○ border | emoji | Toggle ivory border overlay |
| 🔄 convert | emoji | Convert source to PNG via Pillow |

Plus the inherited depth-toggle and delete buttons from BaseNode.

## Data Class

`ImageNodeData` extends `NodeData` with:

- `cache_key: str` — the dotted key into the image cache (`"<sha256>.<ext>"`). Legacy bare-hash keys from v0.1 sessions still resolve.
- `source_path: str` — absolute path to the source file on disk (provenance and drift-check anchor). May be empty for pasted images.
- `caption: str` — editable label, shown on a connected AboutNode rather than painted on the node itself.
- `image_b64: str` — legacy base64-encoded PNG. Always serialized empty in v0.2; retained in `from_dict` for restoring pre-cache sessions.
- `show_border: bool` — ivory border overlay toggle.
- `depth_front: bool` — front/back depth-layer toggle.
- `shelf_visible: bool` — button shelf expand/collapse state.

Default size: 280 × 220.

## Lifecycle

### Creation

`Scene.add_image_node(pos)` → `ImageNode(ImageNodeData())`. Node appears empty with a dashed-line "double-click to load image" placeholder until a file is supplied.

### Session restore

`ImageNodeData.from_dict(d)` reconstitutes the dataclass. `__init__` inspects `cache_key`, `source_path`, and `image_b64` — if any is set, fires the async restore worker. The node shows "loading…" in the placeholder until the worker delivers.

### Removal

`_prepare_for_removal()`:

1. Stops the image delivery timer, disconnects its `timeout` signal
2. Nulls `_pending_pixmap`, `_pending_cache_key`, `_pending_drift`, `_loading`
3. Severs any live `VisionWorker` signals (`finished`, `failed`) — prevents post-deletion callbacks into a dead C++ object
4. Nulls `_pixmap` and `_scaled_cache`
5. Calls `super()._prepare_for_removal()` to let BaseNode tear down its own state

### Serialization

`to_dict()`:

1. If a pixmap exists but no `cache_key` (edge case: pasted image that skipped cache), force-caches it now via `cache_pixmap`
2. Calls `sync_data()` to fold current geometry into the dataclass
3. Returns `data.to_dict()`

The session JSON contains `cache_key` and `source_path`, not the image itself. The image lives in the project's cache directory and travels with the session folder.

### Cache Garbage Collection

`gc_cache(live_keys)` runs on every session save (from `graphics/Scene.py`). It walks the cache directory and removes any file whose name doesn't appear in the live-keys set. Handles both dotted and legacy bare-hash keys. Orphans from stamp re-caches, deleted nodes, or abandoned paste operations are cleaned up silently.

## Technical Notes

- The drop path and restore path both skip the ~540ms PNG encode step that v0.1 required for every large image. Byte-preservation is the single biggest performance win in the ImageNode subsystem.
- `QPixmap.scaled` with `SmoothTransformation` is faster than `FastTransformation` at 2048px and above — Qt's SIMD-vectorized bilinear scaler beats nearest-neighbour's scattered-cache reads on large buffers. We use smooth everywhere.
- The LOD cache is quantized to 0.5-step zoom levels intentionally — continuous-zoom regeneration would pin a CPU core.
- `_scaled_cache_size` is keyed on target pixel dimensions, not image rect dimensions. This is what makes zoom-in stay crisp: the cache regenerates at screen-pixel resolution, not node-local coords.
- `_pending_drift` is the Qt-thread-safe way to hand a drift warning from the worker to the main thread. The worker stores a string; the delivery timer reads it and spawns the AboutNode under the GIL.
- The cache directory is per-project (`set_cache_root` points it at `Documents/Data/Cache/` under the active project root). Different sessions don't share caches.
