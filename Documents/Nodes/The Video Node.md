# The Video Node

The video playback node. Drag-and-drop a file from Explorer, or double-click to browse — VideoNode handles it and puts a live player on the canvas. Behind the frame sit two pieces of infrastructure that were absent in the first-pass implementation and now mirror the ImageNode pipeline: a **shared byte-preserving media cache** (permanence for the graph) and **LOD-adaptive rendering** (crisp at extreme zoom without blowing the memory budget in an animatic of hundreds of clips).

The cache is not a speed feature. It is the load-bearing contract that says *once a video has been bound to this graph, it is a permanent fixture of that graph* — regardless of what happens to the source on disk. Drives can dismount, hands can tidy, network shares can flap; the graph still plays.

## Core Files

| File | Purpose |
|---|---|
| `nodes/VideoNode.py` | The node — paint, playback controls, drift worker, cache ingest |
| `data/VideoNodeData.py` | Pure Python dataclass — `cache_key`, `source_path`, size/mtime fingerprints, playback state |
| `utils/persistence/media_cache.py` | SHA-256 content-addressed byte-preserving cache (shared with ImageNode) |

## How It Works

### Three Ways to Create

1. **Drag-and-drop from Explorer** — `IntricateView.dropEvent` creates the node and calls `load_from_path`
2. **Double-click an empty video area** — opens a file browser at the last used directory
3. **Session restore** — `_restore_from_session` picks source first, falls back to cache second, placeholder third

### The Cache — Byte-Preserving, Content-Addressed, Shared

The media cache lives at `Documents/data/cache/` under the active project. Videos are keyed as `<sha256>.<ext>` exactly like images. Keys are globally unique by SHA; image and video files coexist in the same directory with no collision risk and no subfolders.

Large files use `cache_source_file(path)` which streams through 1 MiB chunks: one pass for the SHA, one pass for a `shutil.copyfile`. Already-cached files short-circuit to hash-only. A 2 GB video hashes in ~6 s on local NVMe and is written verbatim — no transcode, no re-encode, nothing that could change a byte.

**Permanence contract:** when a video is dropped, the node immediately shows playback from the source path (zero wait). A daemon thread caches the bytes in the background and stamps `data.cache_key` on completion. From that instant forward, the graph remembers the video even if the source is moved, deleted, or lives on an unmounted drive.

### Async Pipeline

Three background workers, one main-thread delivery timer:

| Worker | Fires on | Writes |
|---|---|---|
| Cache ingest | drop, pre-cache restore | `_pending_cache_key`, `_pending_size`, `_pending_mtime` |
| Drift check  | restore with extant source | `_pending_drift` |
| Refresh (sync) | Refresh Media Cache menu | `data.cache_key` directly |

A `QTimer` at 100 ms on the main thread (`_check_cache_delivery`) atomically folds pending fields into `data.*` under the GIL and spawns an AboutNode for any pending drift message.

### Session Restore Preference Order

`_restore_from_session()` walks three cases:

1. **Source file on disk exists** → bind source, restore `playback_pos`, schedule background drift check.
2. **Source missing, cache_key resolves** → bind the cached copy. Spawn an AboutNode: *"source missing — playing from cache"*. The graph self-served.
3. **Neither** → empty placeholder. Node stays in the graph, ready to receive a fresh load.

In all three "with-source" branches the node is marked `_viewport_visible = False` and stashes `_pending_autoplay = data.was_playing`. Actual playback is gated on the post-load visibility sweep — see **Viewport Culling**. The position seek itself runs the moment the decoder reports `LoadedMedia` regardless of visibility, so when a clip later fades in it lands frame-accurate at its saved scrub position.

### Drift Detection (Cheap Fingerprint, Then Rehash)

Full SHA-256 of a multi-gigabyte video on every session open would be an IO storm in a 200-clip animatic. So the drift worker uses a two-stage check:

1. `os.stat()` — compare `size` and `mtime` to the values stored on the data class. If both match within 1 s of mtime, the file is clean. **Session open for 200 clean videos costs 200 stat calls, sub-second total.**
2. Only if a fingerprint mismatched do we spend a full streaming SHA to confirm real content drift. If the live hash disagrees with the `cache_key`'s hash portion, spawn an AboutNode on the canvas: *"source drifted — cache no longer matches"* plus the filename.

We **never auto-heal.** If the source on disk has changed, the user sees the drift signal and decides what to do: refresh the cache (accept the new version), investigate the source, or revert the change externally. The cache remains pointing at the version it was bound to.

### Cache Refresh

Right-click the empty space on the titlebar → **Refresh Media Cache**. Unified action for images and videos — purges the cache directory (`send2trash`, recycle bin not hard delete), then walks every live `ImageNode` and `VideoNode`. For videos:

1. If `source_path` exists: hash it, compare to prior `cache_key` (counts drift for the report), re-ingest via `cache_source_file()` synchronously (menu action is user-driven, worth the wait for confirmation), stamp new size/mtime.
2. If no source: the cached key is gone (just purged) — the node will need a fresh binding.

Report: `Media cache refreshed — N item(s) (M had drifted)`.

### LOD-Adaptive Rendering

The previous implementation scaled every incoming frame down to node-rect size at ingest time (memory-light) and then re-scaled to the same size at paint time. At high canvas zoom the painter upsampled a small bitmap → pixelation. The fix cannot be "keep the full-resolution frame around" because a 4K clip at 33 MB per frame across 200 simultaneous videos is 6.6 GB of buffers.

The resolution is to size each incoming frame at ingest time to **video_rect × current view LOD**, capped at source resolution. Memory becomes proportional to *what is on screen*, not to what was decoded.

**Reading the LOD from outside `paint_content`.** `_on_frame` has no painter, so LOD is read from `scene().views()[0].transform().m11()`, quantized to 0.5 zoom steps. One-view assumption matches Intricate today; falls back to 1.0 if no view has attached yet (early restore). `paint_content` reads LOD the normal way from `painter.worldTransform().m11()`.

**Memory profile under this model:**

| Scenario | Per-video | Total |
|---|---|---|
| 90-minute animatic view, 200 clips zoomed out, LOD ≈ 0.3 | ~8 KB frame | ~1.6 MB |
| Zoomed to one shot, LOD ≈ 4, HD source | up to 8 MB for that one | 8 MB + ~8 KB × 199 |
| Pinch-zoom on a 4K clip | capped at 33 MB for that one | others unchanged |

The cap is an overlay effect — as zoom exceeds what the source can provide, Qt's `SmoothPixmapTransform` handles the residual gracefully rather than nearest-neighbour blocking.

**Paused videos + zoom-in.** Playing videos pick up a new LOD on the next frame within 16–33 ms (imperceptible). Paused videos won't receive a new frame until asked, so `paint_content` detects an LOD delta past the quantized step and fires `QTimer.singleShot(0, setPosition(position))` to nudge the decoder into re-emitting the current frame at the new size. The `_last_lod` latch prevents thrash.

### Playback State

Standard QMediaPlayer wiring — `setVideoOutput(QVideoSink)` → `videoFrameChanged` → `_on_frame`. Persisted across session save/load: volume, mute, looping, playback position, and was-playing flag.

Caller intent flows through a single `_pending_autoplay` flag consumed by `_on_media_status` on the `LoadedMedia` transition:

| Caller | Sets `_pending_autoplay` to |
|---|---|
| `load_from_path` (drag-drop, file browser) | `True` (default — flips to `False` only for the rare paused-load caller) |
| `_restore_from_session` | `data.was_playing` |
| GitNode plushie etc. | explicit `autoplay=True` |

When `LoadedMedia` fires: if the intent is set AND `_viewport_visible` is `True`, the player plays immediately; if the intent is set but the node is off-screen (typical mid-session-restore where the camera hasn't settled yet), the intent is stashed into `_was_playing_before_cull` so the next visibility-on transition can fade in cleanly. This is the only mechanism — no path calls `play()` directly on `LoadedMedia`.

### Viewport Culling

`_viewport_visible` tracks whether the node is inside the visible scene rect. When a video leaves the viewport, playback pauses (fades volume first); when it returns, it resumes if it was previously playing. In an animatic view with 200 clips, this keeps decoder load proportional to what the user can actually see.

The cull system also **gates session-load playback**. During `load_session`, every restored video defaults to `_viewport_visible = False` with `_pending_autoplay = data.was_playing`. As each decoder reports `LoadedMedia` (often mid-load, during the `processEvents` yields in the restore loop), the handler sees not-yet-visible and parks the play intent into `_was_playing_before_cull` instead of calling `play()`. After the load completes, `_load_session_into_scene` schedules a single deferred settle: apply the saved camera position, then `view._notify_viewport_changed()` runs the visibility sweep — in-view clips fade in via the standard cull-resume path, off-view stay paused. Without this every was-playing clip in the session blasted ~1 s of audio at the moment of load.

## Data Class

`VideoNodeData` extends `NodeData` with:

- `source_path: str` — absolute path to the source video (provenance anchor, drift-check target)
- `cache_key: str` — dotted key into the shared media cache; *once bound, permanent*
- `source_size: int` — cheap drift fingerprint (bytes at cache time)
- `source_mtime: float` — cheap drift fingerprint (mtime at cache time)
- `caption: str` — editable label shown at the bottom
- `volume: int` — 0–100, persisted
- `playback_pos: int` — milliseconds into the video at save time
- `looping: bool` — whether playback loops
- `muted: bool` — audio mute state
- `show_border: bool` — ivory border overlay toggle
- `was_playing: bool` — whether the node was playing at save time

Default size: 360 × 280.

### Interaction & Resize Polish

The bottom-right corner is a **128×128 symmetric resize zone** — `_resize_grip = 64`, `_resize_overreach = 64`. The hit area extends 64 px inward into the body and 64 px outward past the rect, so a quick "aim approximately at the corner" lands cleanly whether the cursor falls slightly inside or slightly outside the visible edge.

The button-strip shelf reveals via the same **resize-driven gesture AboutNode uses**, not a top-strip double-click. Drag the corner downward past +75 px from press-time height to reveal the shelf; drag back upward past −30 px to tuck it away. The asymmetric thresholds (`_RESIZE_SHELF_REVEAL_THRESHOLD`, `_RESIZE_SHELF_HIDE_THRESHOLD`) are deliberate — reveal demands a deliberate yank, hide is lighter so the user can dial the final height down without the shelf clinging. Anchor re-seeds after every toggle so a single continuous drag can flip the shelf multiple times.

Double-click on the video area still toggles play/pause (or opens the file browser when the node is empty). Double-click on the top strip is purely visual now — no shelf gesture there.

The progress bar ends short of the resize zone with an **end-of-bar marker** (a short vertical tick mirroring AudioNode), so a quick resize-grab can't snag mid-scrub. A defensive `in_resize_zone` bypass in `mousePressEvent` is belt-and-braces — survives future geometry shifts.

## Lifecycle

### Creation

`Scene.add_video_node(pos)` → empty VideoNode. Double-click to browse, or drop a file from Explorer.

### Drop

1. `load_from_path(path)` sets source, marks `_pending_autoplay = True` (the default — drag-drop should roll)
2. `_on_media_status(LoadedMedia)` fires when the decoder is ready and calls `play()` (node is in-view by definition — the user just dropped a file on the canvas)
3. Caption AboutNode spawns if the node had no existing caption
4. Daemon thread runs `cache_source_file(path)` — hash + copy
5. Delivery timer folds `cache_key`, `source_size`, `source_mtime` into the data class
6. From this point forward the graph knows the video permanently

### Session Restore

See **Session Restore Preference Order** above. Source takes precedence (bind source, seek to `playback_pos`, background drift check); cache is the fallback; placeholder if both are gone. Playback itself doesn't kick in until the post-load visibility sweep — see **Viewport Culling** for the audio-blast deferral.

### Removal

Teardown is driven by BaseNode's demolition crew. VideoNode declares its moving parts via class-level flags and supplies a bespoke `_demolition_pre` for the QMediaPlayer pipeline — on Windows / WMF the severance order is load-bearing or the decoder thread raises `STATUS_HEAP_CORRUPTION` (0xc0000374) in ntdll on queued events that land post-`deleteLater`.

Declarative flags consumed by the crew:

```python
_demolition_thread_flag = '_destroyed'
_demolition_timers      = [('_cache_poll', '_check_cache_delivery')]
_demolition_animations  = [('_volume_anim', ['finished'])]
```

Crew sequence per node:

1. `_destroyed = True` — background ingest/drift workers bail on the next check (see `_check_cache_delivery`, `_start_drift_check`)
2. `_cache_poll` timer stopped, `timeout` disconnected
3. `_volume_anim` `finished` disconnected, animation stopped
4. `_demolition_pre`:
   - Null pending fields (`_pending_cache_key`, `_pending_drift`, `_pending_size`, `_pending_mtime`)
   - `blockSignals(True)` on player / sink / audio — covers QMediaPlayer internal emissions (`playbackStateChanged`, `errorOccurred`, `bufferProgress`, `sourceChanged`) we never connected to but WMF can still fire post-disconnect
   - Fade volume to zero so the audio sink drains cleanly
   - `disconnect()` outgoing connections on all three
   - `setSource(QUrl())` to flush the WMF decoder, then `stop()`, `setVideoOutput(None)`, `setAudioOutput(None)`, `deleteLater()` on each
   - Drop the Python wrapper refs (`_player`, `_sink`, `_audio` set to `None`)
5. `_demolition_post`: null frame pixmap and scaled cache

Shake-delete adds one extra synchronous step **before** the particle burst: `_quiet_for_shake` runs `setSource(QUrl()) + stop()` so the WMF decoder detaches while Python and Qt are both fully alive. Without it, the 8000-sprite particle window kept the decoder running on partially-freed pipeline state and occasionally fastfailed inside WMF on malformed media before Qt could emit a catchable signal.

Cache files are **not** removed here — the user may undo the delete, or the removed node's cache entry may have been referenced by the undo snapshot. Orphan cleanup happens on session save via `gc_cache()`.

### Cache Garbage Collection

`gc_cache(live_keys)` runs on every session save from `graphics/Scene.py`. The live-keys set now draws from both image **and** video nodes — unified cache, unified GC. Any file in the cache directory whose name doesn't match a live key gets removed silently.

## Technical Notes

- The paint-time LOD cache is the **second** of two tiers — the ingest-time size is already screen-aware, so the `_scaled_cache` at paint time is only a light aspect-fit to `vr_size`. `SmoothPixmapTransform` is enabled so any painter-side residual is bilinear.
- The `_frame_pending` throttle is unchanged by the cache rewrite — if the paint loop hasn't caught up to the previous frame, the next one is dropped. This keeps decoder pressure bounded even under heavy paint load.
- The cache is shared across projects only to the extent that projects share a `Documents/data/cache/` root. Different `set_cache_root()` targets give isolated caches.
- `cache_source_file` is idempotent. Re-dropping the same video from the same path is a no-op after the first hash pass.
- The drift worker uses a 1-second tolerance on mtime comparison — some networked filesystems round mtime to the nearest second, and exact-equality tripped false positives during testing.
- Playing videos refresh their LOD automatically on the next decoded frame. Paused videos refresh via a `QMediaPlayer.setPosition()` nudge gated on an LOD delta past the quantized step; this avoids decoder thrash during continuous pan/hover.

## History — The PyAV Experiment (2026-04-28 → 2026-04-29)

For one day VideoNode ran on PyAV (libav* via Python), with a per-node decoder thread, libswscale-sized frames, and a bounded ring buffer for ping-pong loops. On paper it was the elegant move: no codec roulette, frame-accurate seek, ping-pong from RAM, no QMediaPlayer heap-corruption pressure. In practice it gave inconsistent fps, pixelated resolution swings, and outright crashes — a measurable downgrade from the QMediaPlayer pipeline that preceded it.

We rolled it back the next morning. The whitepaper wins didn't survive contact with a working day. The lesson, recorded for future-me reading this cold: probes are welcome, but a dependency that proves worse in lived use gets deleted cleanly — no hardening pass, no "let's tune it further", no carrying it forward "in case we revisit". If we revisit a different decoder backend later, it'll be a fresh trial against this baseline (the eventual interest is ffmpeg-direct as a subprocess, not via PyAV).

Visual polish that landed during the PyAV interlude (symmetric resize zone, shelf reveal via resize gesture, short progress bar + end-of-bar marker) was decoder-agnostic and survived the revert intact.
