# Media Cache

The content-addressed, byte-preserving media store that backs every image-like node on the canvas. Images, videos, stickers — anything with a pixmap or a media file on disk flows through the same cache, sharing one directory per project and one deduplication namespace. This document describes the framework — the node-level integration is covered in each node's dedicated doc.

## Design Principles

The cache is a single-purpose primitive with four invariants. Everything else is consequence.

### 1. Content-addressed keys

Every cache entry's name **is** a SHA-256 hash of its bytes, concatenated with a self-describing extension:

```
<sha256>.<ext>
```

- `3a7f…b2c1.jpg` — a JPEG whose bytes hash to `3a7f…b2c1`
- `8e04…1fdd.png` — a PNG whose bytes hash to `8e04…1fdd`
- `c9a2…7733.webp` — a WebP, likewise

The filename tells you everything you need to know about the file without opening it: the hash lets you verify byte-identity, the extension tells the OS (and Qt's decoders) how to open it, and the two together guarantee that no registry of metadata is ever needed outside the filename itself. Lose the session JSON and you can still walk the cache and identify every file by its format and its hash.

**Legacy compatibility.** v0.1 keys were bare hashes (no extension). `load_cached` and `gc_cache` both resolve a bare-hash key to `<key>.png` by fallback — all pre-v0.2 sessions open without migration.

### 2. Byte-preserving

The bytes on disk are **identical** to the bytes of the source file. No re-encode, no re-save, no QPixmap round-trip. `cache_source_bytes(raw, ext)` writes the raw buffer verbatim; `cache_source_file(path)` stream-copies the file.

Why this matters:

- **EXIF** survives — camera model, GPS, capture time, orientation flags.
- **XMP** survives — Adobe sidecar data, ratings, colour labels, edit history, tool provenance.
- **ICC profiles** survive — embedded colour spaces.
- **tEXt chunks** survive — Intricate's own `read_png_vision_stamp` captions, other tools' custom metadata.
- **Format** survives — JPEG stays JPEG, PNG stays PNG, WebP stays WebP. No alpha loss on re-encode, no chroma subsampling, no quantisation drift.

Every byte of every stamp, provenance mark, and embedded colour profile that the user's source files ever acquired is preserved verbatim. The cache is a time capsule, not a compression layer.

**Fallback path.** For images that have no source file on disk (pasted pixmaps, Vision-generated frames), `cache_pixmap(pixmap)` PNG-encodes the in-memory pixmap and caches that. This is the one place where a round-trip happens, and only because there's no choice — the bytes didn't exist as a file to begin with.

### 3. Free deduplication

Two nodes loading the same source file produce the same SHA-256 and therefore the same filename. The second write is skipped (`path.exists()` early-return). No ref-counting, no second-pass compare, no index.

- Ten image nodes pointing at the same 6MB RAW: one cached copy.
- Fifty stickers of the same logo PNG: one cached copy.
- A sticker and an image node showing the same file: one cached copy.

The dedup is an emergent property of content addressing. Nothing in the cache module knows it's happening.

### 4. Retention by reference

On every session save, `gc_cache(live_keys)` walks the cache directory and removes any file whose name (or stem, for legacy keys) does not appear in `live_keys`. The live set is built from every node type in `_CACHED_TYPES` that has a non-empty `cache_key` field.

This is the only garbage-collection mechanism. No TTL, no LRU, no size cap. If a node carrying a key is still in the session, its bytes stay. If the node is deleted and the session saved, the bytes are swept on that same save. Simple, correct, and the user's session file is the authoritative map of what's live.

A 70-node image session's GC pass completes in under 100ms. Cache directory size is bounded by the visual weight of the session — not by the history of the session.

## The API Surface

All exported from `utils/media_cache.py`:

| Function | Purpose | When to use |
|---|---|---|
| `set_cache_root(project_data_dir)` | Point the cache at the active project's data directory. Called once per project load. | `main_window` on project switch. |
| `cache_dir()` | Return the absolute cache directory path. Creates it if missing. Falls back to Intricate's own `Documents/data/cache` if no project is set. | Internal; rarely called by consumers. |
| `cache_source_bytes(raw, ext)` → key | Hash + write raw bytes. Verbatim, dedup. | Any node reading a file and wanting the cache to mirror those exact bytes (ImageNode, StickerNode drop path). |
| `cache_source_file(src_path)` → key | Stream-hash and stream-copy a source file in 1 MiB chunks. Avoids loading the whole file into memory. | VideoNode — video files are large enough that `read_bytes()` is wasteful. |
| `cache_pixmap(pixmap)` → key | Fallback for pasted or generated images with no file origin. PNG-encodes the in-memory pixmap. | ImageNode paste path, StickerNode `to_dict` fallback for never-cached stickers. |
| `load_cached(key)` → QPixmap \| None | Load a pixmap by key. Accepts dotted or legacy bare keys. | Session restore for any node with a stored `cache_key`. |
| `cached_path(key)` → Path \| None | Return the absolute path to the cached file. Accepts both formats. | QMediaPlayer and any consumer that needs a filesystem path rather than a pixmap. |
| `cached_bytes(key)` → bytes \| None | Raw cached file bytes. | Re-hashing, re-caching after stamp writes, drift verification. |
| `hash_file(path)` | Streaming SHA-256 of a file on disk. | Drift check comparing current source against cached hash. |
| `key_hash(key)` | Extract just the hash portion of a key. Handles both formats. | Drift check comparison (cache_key hash vs freshly-hashed source). |
| `gc_cache(live_keys)` → int | Remove any cache file not in `live_keys`. Returns removal count. | Called once per session save by `graphics/Scene.py`. |

Nine functions. No class, no singleton, no state object to pass around. The module is its own namespace and the `_cache_root` module-level is the only mutable state — set once on project load, read everywhere else.

## Integration Points

Currently-consuming files (as of 2026-04-18):

| File | Uses | Pattern |
|---|---|---|
| `nodes/ImageNode.py` | `cache_source_bytes`, `cache_pixmap`, `load_cached`, `cached_bytes`, `hash_file`, `key_hash` | Async worker thread + main-thread delivery timer. Drift check on restore. |
| `nodes/VideoNode.py` | `cache_source_file`, `cached_path` | Stream-copy on drop, player loads from cached path. |
| `nodes/StickerNode.py` | `cache_source_bytes`, `cache_pixmap`, `load_cached`, `hash_file`, `key_hash` | Synchronous load + drift check. Simpler than ImageNode because stickers don't need the LOD pipeline. |
| `graphics/Scene.py` | `gc_cache` | Once per session save. Live-keys set built from `_CACHED_TYPES` whitelist. |
| `main_window.py` | `set_cache_root`, `cache_dir`, manual GC trigger (sidebar menu) | Project-switch wiring + user-initiated full refresh. |

## Passive Drift Detection

The cache is one half of a pair. The other half is the source file on disk, wherever the user originally dropped the image from. The cache preserves the bytes as of the moment of first ingest — it does not sync with the source going forward.

**Drift** happens when the source file on disk changes after ingest but before the cached bytes are refreshed:

- Adobe or another tool wrote its own metadata chunks into the source.
- The source was resized, retouched, re-saved in another app.
- A different image was copied over the source path.

Nodes that care about drift (ImageNode, StickerNode) run a two-tier check on every session restore:

1. **Fingerprint** — compare source `(size, mtime)` against the values stamped at last-cache-time. Matches → no drift, skip.
2. **Hash** — on fingerprint mismatch, stream-hash the current source and compare against `key_hash(cache_key)`. Matches → no drift (file was rewritten identically, e.g. a touch), update the fingerprint. Mismatches → real drift, queue a warning.

On confirmed drift, an AboutNode spawns on the canvas next to the node with the filename. **The cache is not auto-updated.** Policy is flag-don't-auto-fix: the user decides whether the drift is a drift, a correction, or a stamp they want to pull in. A manual Refresh Cache action in the sidebar re-reads every live node's source and updates the cache entries in bulk.

Cost of the drift check: one `stat()` per node on restore (fingerprint path, hot case), plus one streaming SHA per node that actually drifted (rare). For a 70-node session, total overhead is measured in tens of milliseconds, and runs on the background worker (ImageNode) or in-line at restore (StickerNode, which is already an async-free load).

## Per-Project Cache Directories

`set_cache_root(project_data_dir)` points the cache at `<project>/Documents/data/cache/`. Different sessions under different project folders do not share cache contents.

Rationale:

- **Portability** — moving a project folder moves its media with it. Zip the project, send it to a collaborator, and every node's cached bytes travel along. No "please also send me your global cache" footnote.
- **Isolation** — two projects happening to load the same file get one cached copy each (in their own cache dirs). Trades dedup across projects for clean separation. Empirically this is the right trade: users don't want one project's GC sweeping another project's files.
- **Reproducibility** — a project folder is a self-contained snapshot of its own visual state. The cache directory is part of that snapshot.

## Adding a New Cached Node Type

When a new node type wants to participate in the cache:

1. Add `cache_key: str = field(default="")` to its `NodeData` subclass. Add `source_path: str`, `source_size: int`, `source_mtime: float` if drift detection applies.
2. In the node's load path, call `cache_source_bytes` / `cache_source_file` / `cache_pixmap` as appropriate. Write the returned key into `data.cache_key`.
3. In `to_dict`, if `self._pixmap` exists but `self.data.cache_key` is empty, call `cache_pixmap` as a safety net.
4. In the node's session-restore branch, try `load_cached(self.data.cache_key)` first, then fall back to `source_path`, then `image_b64` legacy.
5. Add the new node's type string to `_CACHED_TYPES` in `graphics/Scene.py`'s `gc_cache` call site. Without this, the node's cached bytes will be swept on the next save.
6. If drift detection is wanted, mirror the fingerprint/hash pattern from `StickerNode._load_from_cache_with_drift_check` or `ImageNode._image_load_worker`.

No changes to `utils/media_cache.py` itself are usually needed — the API is stable and covers every ingest shape Intricate has encountered so far (file read, file stream, pixmap encode).

## Technical Notes

- SHA-256 is used over faster hashes (BLAKE3, xxHash, MD5) for its ubiquity — every platform's stdlib has it, no vendored dependency, no versioning risk. Hash cost is not a bottleneck: streaming SHA at 1 MiB chunks saturates modern disk bandwidth.
- `cache_source_bytes` reads the full source into memory. For files > ~50 MB (videos, large RAWs), prefer `cache_source_file` to avoid the allocation spike.
- `cache_pixmap` always writes PNG. JPEG paste would lose alpha; WebP paste would depend on Qt version availability.
- The cache directory does not create subdirectories or any hierarchy — all files live flat in `cache/`. A 500-file session is fine; a 50,000-file session might hit NTFS directory-size inefficiency. No such session has been observed.
- `gc_cache` walks `iterdir()` once per save. On a project with a 10,000-file cache, this takes ~30-50ms on SSD. Acceptable as a synchronous step inside `_save_session_and_teardown` given how rare that path is.
- The cache module does not depend on anything in `nodes/` or `graphics/`. It only imports `hashlib`, `pathlib`, PySide6 QBuffer/QImage/QPixmap, and the shared logger. This one-way dependency keeps the cache a true primitive — testable in isolation, replaceable without touching any node.

## Relationship to Other Systems

- **PNG stamping** (`utils/persistence/png_stamp.py`) — writes `Intricate: <caption>` tEXt chunks into source PNG files. Post-stamp, `ImageNode` re-reads the stamped bytes and re-caches. The pre-stamp entry becomes an orphan and gets swept on the next save.
- **Vision API** (`utils/vision.py`) — operates on `source_path` for the cold call, or on `cached_bytes(cache_key)` for the hot call. The cache is deliberately independent of Vision — nothing in `media_cache` knows Vision exists.
- **Session save/load** (`utils/session.py` + `graphics/Scene.py`) — the session JSON carries `cache_key` per node, not bytes. On restore, each node resolves its key through the cache. If the cache directory is gone, nodes fall back to `source_path` and re-cache.
