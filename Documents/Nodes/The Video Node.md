# The Video Node

The video playback node. Drag-and-drop a file from Explorer, or double-click to browse — VideoNode handles it and puts a live player on the canvas. Behind the frame sit two pieces of infrastructure: a **shared byte-preserving media cache** (permanence for the graph) and **LOD-adaptive rendering** (crisp at extreme zoom without blowing the memory budget in an animatic of hundreds of clips). The decoder beneath is **PyAV** (libav* directly via ffmpeg's Python bindings), not QMediaPlayer.

The cache is not a speed feature. It is the load-bearing contract that says *once a video has been bound to this graph, it is a permanent fixture of that graph* — regardless of what happens to the source on disk. Drives can dismount, hands can tidy, network shares can flap; the graph still plays.

## Core Files

| File | Purpose |
|---|---|
| `nodes/VideoNode.py` | The node — paint, playback controls, drift worker, cache ingest, decoder lifecycle |
| `data/VideoNodeData.py` | Pure Python dataclass — `cache_key`, `source_path`, size/mtime fingerprints, `loop_mode`, playback state |
| `utils/video_decoder.py` | PyAV-backed decoder thread; LOD-aware ingest, loop / ping-pong / off modes |
| `utils/persistence/media_cache.py` | SHA-256 content-addressed byte-preserving cache (shared with ImageNode) |

## How It Works

### Three Ways to Create

1. **Drag-and-drop from Explorer** — `IntricateView.dropEvent` creates the node and calls `load_from_path`
2. **Double-click an empty video area** — opens a file browser at the last used directory
3. **Session restore** — `_restore_from_session` picks source first, falls back to cache second, placeholder third

### The Decode Backend — PyAV

VideoNode's decode path is `utils.video_decoder.VideoDecoder`, a thin wrapper around PyAV. One worker thread per node owns the `av.container`, decodes packets, sizes each frame to LOD via libswscale, and emits Qt signals back to the main GUI thread. The previous QMediaPlayer + QVideoSink path is gone — see `Documents/Design/A-V Transport Engine — Forward Design Exploration.md` for the staged plan this is part of (Stage 3 of that doc, landed standalone).

What this swap bought:
- **No more codec-roulette.** PyAV uses ffmpeg's libav* directly. Same code path on every machine; no WMF / DirectShow surprises.
- **Native ping-pong.** A bounded in-memory ring buffer captures decoded frames on the forward pass; the reverse pass replays from RAM with no further decode work. See `loop_mode` below.
- **Frame-accurate seek** without the QMediaPlayer "scrub then catch up" lag. Seek hits libav directly.
- **No heap-corruption class.** The 0xc0000374 incident the six-step teardown was built to dodge was a WMF artifact. PyAV teardown is `decoder.close()` — set the stop flag, join the worker thread (bounded), close the container.

Audio is gone from VideoNode entirely (Stage 1 of the design doc). Audio is AudioNode's domain. Old session files carrying `volume` / `muted` / `looping` keys are read back-compat (looping → loop_mode) and the audio fields are silently ignored.

### The Cache — Byte-Preserving, Content-Addressed, Shared

The media cache lives at `Documents/Data/Cache/` under the active project. Videos are keyed as `<sha256>.<ext>` exactly like images. Keys are globally unique by SHA; image and video files coexist in the same directory with no collision risk and no subfolders.

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

Plus the PyAV decoder worker (one per VideoNode), which is a different beast — see *Decode Backend* above.

### Session Restore Preference Order

`_restore_from_session()` walks three cases:

1. **Source file on disk exists** → play from source (fast start), schedule background drift check.
2. **Source missing, cache_key resolves** → play from the cached copy. Spawn an AboutNode: *"source missing — playing from cache"*. The graph self-served.
3. **Neither** → empty placeholder. Node stays in the graph, ready to receive a fresh load.

### Drift Detection (Cheap Fingerprint, Then Rehash)

Full SHA-256 of a multi-gigabyte video on every session open would be an IO storm in a 200-clip animatic. So the drift worker uses a two-stage check:

1. `os.stat()` — compare `size` and `mtime` to the values stored on the data class. If both match within 1 s of mtime, the file is clean. **Session open for 200 clean videos costs 200 stat calls, sub-second total.**
2. Only if a fingerprint mismatched do we spend a full streaming SHA to confirm real content drift. If the live hash disagrees with the `cache_key`'s hash portion, spawn an AboutNode on the canvas: *"source drifted — cache no longer matches"* plus the filename.

We **never auto-heal.** If the source on disk has changed, the user sees the drift signal and decides what to do: refresh the cache (accept the new version), investigate the source, or revert the change externally.

### Cache Refresh

Right-click the empty space on the titlebar → **Refresh Media Cache**. Unified action for images and videos — purges the cache directory (`send2trash`, recycle bin not hard delete), then walks every live `ImageNode` and `VideoNode`. For videos:

1. If `source_path` exists: hash it, compare to prior `cache_key` (counts drift for the report), re-ingest via `cache_source_file()` synchronously, stamp new size/mtime.
2. If no source: the cached key is gone (just purged) — the node will need a fresh binding.

Report: `Media cache refreshed — N item(s) (M had drifted)`.

### LOD-Adaptive Rendering

Each frame is sized at decode time to **video_rect × current view LOD**, capped at source resolution, by libswscale inside the decoder thread. Memory becomes proportional to *what is on screen*, not to what was decoded.

**Reading the LOD from outside `paint_content`.** `paint_content` reads LOD via `painter.worldTransform().m11()`, quantizes to 0.5 zoom steps, and pushes any change to the decoder via `decoder.set_lod_size(w, h)`. The decoder picks up the new size on the next decoded frame. For paused videos the decoder reformats the stored `av.VideoFrame` at the new size on the spot — no re-decode needed, just one swscale pass. This is the PyAV-era replacement for the previous `setPosition(position)` nudge.

**Memory profile under this model:**

| Scenario | Per-video | Total |
|---|---|---|
| 90-minute animatic view, 200 clips zoomed out, LOD ≈ 0.3 | ~8 KB frame | ~1.6 MB |
| Zoomed to one shot, LOD ≈ 4, HD source | up to 8 MB for that one | 8 MB + ~8 KB × 199 |
| Pinch-zoom on a 4K clip | capped at 33 MB for that one | others unchanged |

The cap is an overlay effect — as zoom exceeds what the source can provide, Qt's `SmoothPixmapTransform` handles the residual gracefully rather than nearest-neighbour blocking.

### Playback State and Loop Modes

`data.loop_mode` is a tri-state string: **`"off"`** (play once, stop on EOF), **`"loop"`** (seamlessly restart), **`"pingpong"`** (forward to end, then reverse to start, then forward again — a back-and-forth oscillation). The loop button on the node's button strip cycles through the three states.

**Ping-pong implementation.** The decoder thread captures decoded frames into a bounded ring buffer (~256 MiB cap by default — see `PING_PONG_BUFFER_CAP_BYTES` in `utils/video_decoder.py`) on the forward pass. At end-of-stream it stops decoding and walks the buffer in reverse with the same per-frame display durations, then flips to forward and re-decodes from the source. Clips that exceed the buffer cap fall back to `"loop"` semantics with a warning log; the libav-rendered reversed-file fallback for very long clips is left as a future refinement.

The buffer is invalidated whenever the LOD size changes — the captured QImages are now the wrong resolution for the new view zoom — and rebuilds on the next forward pass.

### Viewport Culling

`_viewport_visible` tracks whether the node is inside the visible scene rect. When a video leaves the viewport, the decoder is paused; when it returns, it resumes if the user hadn't explicitly paused. With audio gone from VideoNode the previous fade-to-silence handshake is gone too — cull/uncull is a clean play/pause swap on the decoder. `Scene.update_video_visibility` also handles altitude culling at zoom < `_MEDIA_TINY_RENDER_PX`.

## Data Class

`VideoNodeData` extends `NodeData` with:

- `source_path: str` — absolute path to the source video (provenance anchor, drift-check target)
- `cache_key: str` — dotted key into the shared media cache; *once bound, permanent*
- `source_size: int` — cheap drift fingerprint (bytes at cache time)
- `source_mtime: float` — cheap drift fingerprint (mtime at cache time)
- `caption: str` — editable label shown at the bottom
- `playback_pos: int` — milliseconds into the video at save time
- `loop_mode: str` — `"off" | "loop" | "pingpong"`
- `show_border: bool` — ivory border overlay toggle
- `was_playing: bool` — whether the node was playing at save time

Default size: 360 × 280.

**Removed in the PyAV migration:** `volume`, `muted`, `looping`. The first two never had a runtime owner in VideoNode any more (audio is gone); `looping` was widened into the tri-state `loop_mode`. `from_dict` reads old session files: a `looping=True` value back-compats into `loop_mode="loop"`; `volume` and `muted` keys are silently ignored.

## Lifecycle

### Creation

`Scene.add_video_node(pos)` → empty VideoNode. Double-click to browse, or drop a file from Explorer.

### Drop / browse — initial load

1. `load_from_path(path)` → decoder opens the source via PyAV; first frame arrives within tens of milliseconds and the node sits **paused** on that frame. Initial loads do not autoplay — the user starts playback explicitly.
2. Caption AboutNode spawns if the node had no existing caption
3. Daemon thread runs `cache_source_file(path)` — hash + copy
4. Delivery timer folds `cache_key`, `source_size`, `source_mtime` into the data class
5. From this point forward the graph knows the video permanently

### Session restore — autoplay-on-intent

Session restore is a separate entry point and respects the saved `data.was_playing` flag. Clips that were rolling when the session was saved resume rolling at their saved `playback_pos`; clips that were paused stay paused. The two contracts are intentionally distinct: a freshly-dropped file is a quiet new arrival; a session reopens its own state of motion.

### Session Restore

See **Session Restore Preference Order** above. Source takes precedence (fast playback + background drift check); cache is the fallback; placeholder if both are gone.

### Removal

`_prepare_for_removal()` (via the demolition crew):

1. Sets `_destroyed` flag — background workers check this before writing
2. Stops `_cache_poll` timer and disconnects its `timeout` signal
3. Nulls `_pending_*` fields
4. Disconnects every decoder signal (`frame`, `position`, `duration`, `state`, `error`)
5. `decoder.close()` — sets the stop flag, joins the worker thread (bounded 1 s), closes the av.container
6. Nulls frame pixmap and scaled cache; nulls the decoder reference

`_quiet_for_shake` runs the same close path synchronously at shake-trigger time so the particle burst window has nothing live to dereference. With PyAV the heap-corruption class the old WMF teardown defended against is gone, but the close sequence is still the cleanest bow on a node.

Cache files are **not** removed here — the user may undo the delete, or the removed node's cache entry may have been referenced by the undo snapshot. Orphan cleanup happens on session save via `gc_cache()`.

### Cache Garbage Collection

`gc_cache(live_keys)` runs on every session save from `graphics/Scene.py`. The live-keys set draws from both image **and** video nodes — unified cache, unified GC. Any file in the cache directory whose name doesn't match a live key gets removed silently.

## Build / Bundling Notes

PyAV ships its libav DLLs in `av.libs/` next to the package directory. `build.py` invokes PyInstaller with `--collect-all=av` so the frozen build carries the `av/` package, its `.pyd` extensions, and the `av.libs/*.dll` set together. No system ffmpeg dependency for end-user builds.

## Technical Notes

- The paint-time scaled cache is the **second** of two tiers — the decoder already produces an LOD-sized QImage, so paint-time `_scaled_cache` is just an aspect-fit to `vr_size`. `SmoothPixmapTransform` is enabled so any painter-side residual is bilinear.
- The PyAV decoder thread paces itself against `time.monotonic()` using stream PTS — frames are emitted at their real-time intervals. Dropping a frame in the queue path is a manual operation; today we don't bound the queue (Qt's queued-connection delivery handles backpressure naturally — slow GUI = slow signal delivery).
- `decoder.set_lod_size()` is the public-facing LOD knob. It's a hint; the decoder caps at source resolution so up-zoom past native res doesn't allocate beyond the original frame. Down-zoom always honoured.
- The drift worker uses a 1-second tolerance on mtime comparison — some networked filesystems round mtime to the nearest second, and exact-equality tripped false positives during testing.
- Ping-pong's bounded buffer trades RAM for the absence of seek-restart artifacts at the loop boundary. The 256 MiB cap is conservative; can be raised for users who routinely ping-pong long clips.
- The previous QMediaPlayer-era six-step teardown lives on in spirit as `_quiet_for_shake` + `_demolition_pre`, even though the heap-corruption pressure that motivated it (WMF) is gone with the backend swap. The pattern is cheap and the discipline is good.
