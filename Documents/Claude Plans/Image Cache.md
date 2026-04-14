# Proprietary Image Cache for Intricate

## Context

Images in ImageNodes are currently either file-backed (source_path on disk, base64 zeroed in session) or pasted (full base64 blob stored in session JSON). Problem: if the source file is deleted, the image is gone — the node loads blank. And pasted images bloat the session file with multi-MB base64 strings.

Goal: a local image cache that survives source file deletion. Images stay in the cache as long as at least one node references them. Deleting all nodes referencing a cached image allows it to be garbage-collected.

## Design

### Cache Location

`Documents/data/cache/` — sits alongside session files, inside the existing data directory. Not git-tracked (add to .gitignore).

### Cache Key

SHA-256 hash of the image bytes (after the 2048px downscale). Filename: `{hash}.png`. This gives us automatic deduplication — two nodes loading the same image share one cache file.

### Write Path (ImageNode.load_from_path + paste)

1. Image loads → scale to 2048px max (existing logic)
2. Compute SHA-256 of the pixmap's PNG bytes
3. Write `Documents/data/cache/{hash}.png` if not already present
4. Store `cache_key = hash` on `ImageNodeData` (new field)
5. Keep `source_path` for provenance tracking (where it originally came from)
6. Stop encoding base64 entirely — `image_b64` becomes vestigial (kept for backward compat on load)

### Save Path (ImageNodeData.to_dict)

- Write `cache_key` to session JSON
- Zero out `image_b64` always (cache replaces it)
- Keep `source_path` for reference

### Load Path (ImageNode constructor / session restore)

Priority order:
1. `cache_key` → look up `Documents/data/cache/{key}.png` — load from cache
2. `source_path` → file exists on disk — load from file, write to cache, set cache_key
3. `image_b64` → legacy session data — decode, write to cache, set cache_key
4. All empty → blank node (placeholder)

### Garbage Collection

On session save, collect all `cache_key` values from live ImageNodes. Compare against files in `cache/`. Delete any cache files not referenced by any node. Simple reference-counting without a separate manifest.

### Cache Utility Module

New file: `utils/image_cache.py`
- `cache_pixmap(pixmap: QPixmap) -> str` — write PNG to cache, return hash key
- `load_cached(key: str) -> QPixmap | None` — load from cache by key
- `gc_cache(live_keys: set[str])` — remove unreferenced cache files
- `cache_dir() -> Path` — returns/creates the cache directory

## Files to Modify

- **NEW**: `utils/image_cache.py` — cache read/write/gc
- `data/ImageNodeData.py` — add `cache_key` field, update to_dict/from_dict
- `nodes/ImageNode.py` — use cache in load_from_path, _encode_to_b64 (replace with cache write), constructor restore logic
- `graphics/Scene.py` — call gc_cache on save_session with set of live keys
- `.gitignore` — add `Documents/data/cache/`

## Backward Compatibility

- Old sessions with `image_b64` blobs still load (priority 3 in load path)
- Old sessions with `source_path` only still load (priority 2)
- On first load of an old session, images migrate into cache automatically
- `cache_key` field defaults to `""` — absent in old sessions, handled gracefully

## Verification

1. Load an image into an ImageNode → verify cache file appears in `Documents/data/cache/`
2. Delete the source file from disk → restart Intricate → image still shows (loaded from cache)
3. Delete the ImageNode (shake-delete) → save session → verify cache file is garbage-collected
4. Load an old session with base64 blobs → images migrate to cache, next save has no base64
5. Two ImageNodes with same source file → single cache entry (deduplication via hash)
