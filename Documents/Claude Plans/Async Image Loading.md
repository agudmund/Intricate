# Async Image Loading for ImageNode

## Context

ImageNode loads images synchronously in `__init__`, blocking the main thread during session restore and drag-and-drop. The recently added image cache makes first-time loads especially expensive — PNG encode + SHA-256 hash + disk write all run on the UI thread. With 10K resolution images this freezes the canvas for hundreds of milliseconds per node. VideoNode doesn't have this problem because `QMediaPlayer.setSource()` returns instantly and decodes async.

## Approach

Follow the **daemon thread + QTimer polling** pattern established by MarkdownNode, GitNode, and ClaudeInfoNode. A daemon thread does all heavy I/O and writes the result to a shared field; a 100ms QTimer on the main thread picks it up.

## Files to Modify

- `nodes/ImageNode.py` — main changes
- No changes to `utils/image_cache.py` — called from worker thread as-is

## Changes

### 1. Add shared state + delivery timer (`__init__`)

After the existing `_scaled_cache` fields, add:
- `self._pending_pixmap: QPixmap | None = None`
- `self._pending_cache_key: str | None = None` (sentinel: `""` = done, no cache key)
- `self._loading: bool = False`
- `self._image_delivery_timer = QTimer()` at 100ms, connected to `_check_image_delivery`, initially stopped

Add `import threading` at top of file.

### 2. Replace synchronous restore with thread launch

Replace the try/except block (lines 67-87) with:
```python
if data.cache_key or data.source_path or data.image_b64:
    self._loading = True
    threading.Thread(target=self._image_load_worker, daemon=True).start()
    self._image_delivery_timer.start()
```

Node appears immediately with `_pixmap = None` — paint_content already handles this.

### 3. Implement `_image_load_worker()`

Runs off-thread. Tries the three fallback paths in order:
1. `load_cached(self.data.cache_key)` — disk read
2. `_read_and_scale(path)` → `cache_pixmap()` — file read + scale + cache write
3. `_decode_b64(b64_str)` → `cache_pixmap()` — base64 decode + cache write

Writes `self._pending_pixmap` and `self._pending_cache_key` when done. GIL makes reference writes atomic — same safety model as MarkdownNode's `_pending_html`.

### 4. Extract static helpers

Factor `_restore_from_path` and `_load_from_b64` into static/standalone methods (`_read_and_scale`, `_decode_b64`) that create fresh QImage/QPixmap instances with no widget interaction — thread-safe.

### 5. Implement `_check_image_delivery()`

Main-thread timer callback:
- If `_pending_cache_key is None`, worker still running — return
- Grab pixmap + cache_key, reset pending fields to None
- Stop timer, set `_loading = False`
- Assign `_pixmap`, invalidate `_scaled_cache`, update `data.cache_key`
- `self.update()` to repaint

### 6. Update `_prepare_for_removal()`

Before existing VisionWorker cleanup:
- Stop and disconnect `_image_delivery_timer`
- Null out `_pending_pixmap`, `_pending_cache_key`, `_loading`

Late-finishing daemon thread writes harmlessly to dead fields.

### 7. Update `paint_content()` placeholder

When `_pixmap is None`: show `"loading…"` if `_loading` else `"double-click\nto load image"`.

### 8. Make `load_from_path()` also async

The public method (called from drag-and-drop and file browser) currently does the same synchronous I/O. Apply same pattern: set metadata immediately, clear pixmap, start timer, spawn worker.

### 9. No session restore batching

Each node spawns its own daemon thread. Python GIL yields on I/O so they naturally interleave. No thread pool needed.

## Verification

1. `python main.py` — app launches, session restores without freezing
2. Canvas remains responsive while images load (can pan/zoom during load)
3. Drag-and-drop an image — appears async with "loading…" then the image
4. Delete an ImageNode while it's loading — no crash
5. Large images (10K) load without hanging the UI
6. Cache is generated on first load, subsequent loads use cache (faster)
