# Node Cleanup Compliance

Running log of node-type cleanup fixes applied to `_prepare_for_removal()` across the codebase. Intricate hot-edits its own dataflow graph at runtime, so closing the app while nodes are mid-teardown is a frequent real-world scenario — every node type must survive it gracefully.

---

## The Contract

`BaseNode._prepare_for_removal()` is the single deterministic teardown hook. Every node subclass that adds **any** of the following must override it and clean up before calling `super()`:

- `QTimer.timeout.connect()` — stop **and** disconnect
- `QVariantAnimation.valueChanged.connect()` — stop **and** disconnect
- `QGraphicsProxyWidget` — detach widget, reparent, `deleteLater()`, remove from scene
- Background threads — set a cancellation flag **before** touching Qt objects
- Any other signal connection added in the subclass

`.stop()` alone is never sufficient — it does not sever the C++ signal reference and will cause a GC leak or a dangling-pointer crash.

---

## Fix Log

### 2026-04-15 — MarkdownNode

**Symptom:** Access violation in `Qt6Widgets.dll` on app close. Event Viewer showed exception `0xc0000005` in the Qt paint loop.

**Root cause:** Two issues in `_prepare_for_removal()`:

1. **Daemon worker thread race** — the background markdown→HTML thread could finish and write to `self._pending_html` after teardown had already nulled the proxy and editor. The delivery timer callback would then try to call `setHtml()` on a dead widget.

2. **Proxy widget left in scene graph** — `setWidget(None)` detached the QTextEdit from the proxy, but the `QGraphicsProxyWidget` itself remained a child item in the scene. Qt's C++ paint loop could still reach it after the Python references were gone.

**Fix applied to `nodes/MarkdownNode.py`:**

| Step | What | Why |
|------|------|-----|
| 1 | Added `self._removed = False` flag in `__init__` | Coordination signal between threads |
| 2 | Set `self._removed = True` at top of `_prepare_for_removal()` | Tells worker + timer to bail out |
| 3 | Worker checks `_removed` before writing `_pending_html` | Prevents post-teardown writes |
| 4 | Delivery timer checks `_removed` before touching editor | Prevents post-teardown `setHtml()` |
| 5 | `QTextEdit.setParent(None)` + `deleteLater()` | Detaches widget from proxy and schedules C++ deletion |
| 6 | `scene.removeItem(self._html_proxy)` | Pulls proxy out of scene graph so paint loop can't reach it |

**Verification:** Closed the app while a MarkdownNode delete animation was in progress. Particles faded cleanly through transparency, no crash.

### 2026-04-16 — WarmNode (ghost node after delete)

**Symptom:** Deleting a WarmNode in the Urzula session left it rendered on canvas but unclickable — a ghost. `crash.txt` showed an `AttributeError` traceback ending in `'PrettyEdit' object has no attribute '_restore_view_focus'`.

**Root cause:** Upstream in Pretty Widgets (`PrettyEdit.py`), the helper function `_is_emoji` had been extracted from the class body to module level. The four methods that followed it (`paintEvent`, `_paint_selection_bg`, `_lift_view_focus`, `_restore_view_focus`) were left at 4-space indent below a misleading `# ── PrettyEdit (continued)` comment. Python has no "continued class" syntax — so those methods became nested functions inside `_is_emoji`, invisible to the `PrettyEdit` class at runtime.

**The crash chain:**

1. `_deferred_remove` calls `scene.removeItem(node)`
2. `itemChange` fires → `_prepare_for_removal()` on WarmNode
3. WarmNode calls `self._editor.teardown()`
4. `PrettyEdit.teardown()` calls `self._restore_view_focus()` → **AttributeError**
5. Exception kills removal mid-flight — node stays in scene graph (painted) but with flags zeroed out (unclickable ghost)

**Fix applied to `Pretty Widgets/src/pretty_widgets/PrettyEdit.py`:**

| Step | What | Why |
|------|------|-----|
| 1 | Moved `_is_emoji` above the class definition | Proper module-level helper, defined before first use |
| 2 | Removed `# ── PrettyEdit (continued)` comment | Eliminated the false impression that methods below were inside the class |
| 3 | `paintEvent`, `_paint_selection_bg`, `_lift_view_focus`, `_restore_view_focus` now inside class body | AST confirms 15 methods on `PrettyEdit` (was 11) |

**Collateral fix:** The broken `_lift_view_focus` / `_restore_view_focus` pair also affected the Majestic bridge — view focus management was silently failing for all PrettyEdit-based nodes, not just WarmNode. This single fix restored correct behaviour across the board.

**Verification:** `hasattr(PrettyEdit, '_restore_view_focus')` → `True`. AST parse confirms all 4 methods are class members. WarmNode deletion completes cleanly.

### 2026-04-16 — PrettyEdit proxy widget left in scene graph

**Symptom:** Access violation (`0xc0000005`) in `Qt6Widgets.dll` while rapidly deleting nodes with PrettyEdit editors (WarmNode, AboutNode, etc.). Python teardown completes cleanly — crash occurs in the C++ paint loop one frame later.

**Root cause:** `PrettyEdit.teardown()` called `proxy.setWidget(None)` to sever C++ ownership of the QTextEdit, but left the `QGraphicsProxyWidget` itself in the scene graph as a child of the parent node. When Qt's paint loop reached the zombie proxy, it dereferenced the severed widget pointer → access violation.

This is the same class of bug as the MarkdownNode fix (2026-04-15), but in the shared `PrettyEdit` widget — affecting all 9 node types that embed a PrettyEdit: WarmNode, AboutNode, CodeNode, ClaudeResponseNode, CushionsNode, LogNode, TreeNode (×2), TextNode.

**Fix applied to `Pretty Widgets/src/pretty_widgets/PrettyEdit.py` `teardown()`:**

| Step | What | Why |
|------|------|-----|
| 1 | `proxy.setWidget(None)` | Sever C++ ownership (already existed) |
| 2 | `self.setParent(None)` + `self.deleteLater()` | Detach QTextEdit and schedule C++ deletion |
| 3 | `scene.removeItem(self.proxy)` | Pull proxy out of scene graph so paint loop can't reach it |
| 4 | `self.proxy = None` | Clear Python reference to prevent reuse |

**Verification:** Rapidly deleted WarmNodes and AboutNodes. All `_prepare_for_removal` traces complete cleanly, no `0xc0000005` in Event Viewer.

### 2026-04-16 — VideoNode deferred stop + unparented media objects

**Symptom:** `0xc0000005` in `Qt6Widgets.dll` two seconds after a VideoNode deletion completes cleanly. No Python traceback — pure C++ crash.

**Root cause:** Two issues in `_prepare_for_removal()`:

1. **Deferred player stop** — `QTimer.singleShot(0, self._player.stop)` scheduled the stop for the next event loop tick, *after* `super()._prepare_for_removal()` had already removed the node from the scene. The player could deliver one last frame to the video sink during that window.

2. **Unparented media objects** — `QMediaPlayer`, `QAudioOutput`, and `QVideoSink` were created without a parent. Python GC could collect them in any order after the node was removed. If the sink was collected first while the player still held a C++ reference to it, frame delivery dereferenced a dead pointer.

**Fix applied to `nodes/VideoNode.py`:**

| Step | What | Why |
|------|------|-----|
| 1 | `self._player.stop()` (synchronous) | Stop immediately, no deferred tick |
| 2 | `self._player.setVideoOutput(None)` | Sever player → sink C++ link |
| 3 | `self._player.setAudioOutput(None)` | Sever player → audio C++ link |
| 4 | `.deleteLater()` on player, sink, audio | Schedule C++ deletion in correct order |

**Verification:** Deleted VideoNodes while video was playing. No crash in Event Viewer.

### 2026-04-16 — GitNode loading node dismiss (3-phase fix)

The GitNode's loading plushie (a VideoNode wired to the GitNode during push) went through three fix iterations in this session. Each solved a crash but revealed the next layer.

**Phase 1 — Deferred removal race + glide timer leak**

**Symptom:** `0xc0000005` in `Qt6Widgets.dll` when push completes and the plushie autodestruct fires.

**Root cause:** `QTimer.singleShot(0, _remove)` left the VideoNode in the scene between hide and removal — the player could deliver a frame to the dead sink. Glide timers on wires were stopped but not disconnected.

**Fix:** Added `conn._glide_timer.timeout.disconnect()` on wires. Changed to immediate `scene.removeItem(node)`.

**Phase 2 — Re-entrant scene modification**

**Symptom:** Immediate `removeItem` during event processing caused `0xc0000005` — Qt's C++ internals weren't ready for re-entrant scene modification.

**Root cause:** Calling `_prepare_for_removal()` explicitly before `removeItem()` detached child items (buttons, ports) that Qt's C++ `removeItem` still expected in its internal child list.

**Fix:** Reverted to deferred `removeItem`, but stop the video player and sever media links synchronously beforehand. Let `_prepare_for_removal` fire naturally via `itemChange` during the deferred `removeItem`. Added `_removal_done` guard to `BaseNode` so `_prepare_for_removal` is idempotent.

**Phase 3 — Cross-thread timer delivery + plushie never dismissed**

**Symptom:** Green dots never updated during push, plushie danced forever. Creating a second GitNode showed correct status.

**Root cause:** `QTimer.singleShot(0, callback)` from worker threads doesn't reliably queue into the main thread's event loop in PySide6. The per-future `_kick_refresh` and final `_on_push_done` callbacks were silently dropped.

**Fix:** Replaced all cross-thread `QTimer.singleShot` calls with a flag-based pattern:
- Worker thread sets `_push_dirty = True` per completed future, `_push_complete = True` when all done
- `_delivery_timer` (250ms, main thread) polls these flags
- `_push_dirty` triggers a rescan → green dots update in real time
- `_push_complete` triggers dismiss + cleanup → plushie explodes

**Final state of `_dismiss_loading_node()`:**

| Step | What | Why |
|------|------|-----|
| 1 | `conn._glide_timer.stop()` + `.disconnect()` | Sever wire timer signals |
| 2 | Strip wires, null node refs, `removeItem(conn)` | Clean wire removal |
| 3 | `node._player.stop()` + `setVideoOutput(None)` + `setAudioOutput(None)` | Stop frame delivery before deferred window |
| 4 | `setVisible(False)` + zero flags | Node inert during deferred tick |
| 5 | `QTimer.singleShot(0, removeItem)` | Deferred removal — `_prepare_for_removal` fires via `itemChange` |

**Final state of `_check_delivery()`:**

| Flag | Action |
|------|--------|
| `_push_dirty` | Spawn a rescan thread if not already scanning |
| `_push_complete` | Set `_pushing = False`, dismiss plushie, restart poll timer, final rescan |
| `_pending_repos` (non-push) | Stop delivery timer, dismiss plushie, update `_repos` + repaint |
| `_pending_repos` (mid-push) | Keep delivery timer alive, update `_repos` + repaint |

**Lesson learned:** Never use `QTimer.singleShot` to cross thread boundaries in PySide6. Use flags polled by a main-thread timer, or proper `QMetaObject.invokeMethod` with `Qt.QueuedConnection`.

### 2026-04-17 — Peer-paint-during-burst class of crash

**Symptom:** `0xc0000005` access violation in `Qt6Widgets.dll` ~5 seconds after the last `_prepare_for_removal complete` log line. The log terminates mid-sequence during a bulk housekeeping pass (163 nodes removed in 21 s on a 1200+ node session with dozens of nodes running shake/pulse animations concurrently). Python teardown phases all ran cleanly — no traceback. Faulting module is `Qt6Widgets.dll`, not `Qt6Gui.dll`, placing the fault in the embedded-widget / proxy / paint pipeline rather than the scene graph core.

**Root cause — new angle.** Every per-node-type `_prepare_for_removal()` is already compliant (prior fixes dated 2026-04-15 / 2026-04-16). The fault is not in any individual node's teardown. It is **cross-node**: during the destruction burst, surviving peers' per-frame mutators keep firing into the event loop —

| Surviving-peer signal | Target | Effect |
|-----------------------|--------|--------|
| `NodeBehaviour.bg_anim.valueChanged` | `setBrush()` | Invalidates paint region on peer |
| `NodeBehaviour.pulse_anim.valueChanged` | `setScale()` | Invalidates paint region on peer |
| `Connection._glide_timer` (16 ms) | `_build_bezier()` + `update()` | Repaints the wire |

These tick while some sibling node's `deleteLater()` is still draining. When a wire paint or peer repaint resolves, it dereferences `Connection.start_node` / `end_node` — a Python reference whose underlying C++ `QGraphicsItem` has already been destroyed. `Qt6Widgets.dll` reads freed memory → access violation.

The removal path itself is intentionally fast (it sometimes outruns the Qt event loop) and must stay fast. The fix is to quieten the peers for the duration of the burst, not to slow the destruction.

**Fix applied (three parts):**

**1. Scene-level quiescence counter** (`nodes/BaseNode.py::_shake_delete_group`).
A counter on the scene (`scene._bulk_removing`) is raised before the deferred-removal loop and lowered two event-loop ticks after the last `QTimer.singleShot(0, removeItem)` — the double-defer guarantees that any repaint scheduled *by* those removals still sees the flag raised. A counter (not a boolean) composes safely across overlapping bursts.

**2. `Connection` endpoint validity guards** (`graphics/Connection.py`).
`_endpoint_alive(node)` uses `shiboken6.isValid()` + `node.scene() is not None` to confirm a peer is safe to paint against. Guards added in two hot paths:
- `Connection.paint()` — early-return if either endpoint is not alive.
- `Connection._glide_tick()` — early-return if either endpoint is not alive; also early-return if `scene._bulk_removing > 0`. Dead endpoints cause the timer to stop itself.

**3. `NodeBehaviour._on_bg_changed` peer quiescence** (`nodes/NodeBehaviour.py`).
Early-return if the node's scene has `_bulk_removing > 0`. The final target colour still resolves correctly once the burst ends — only interim frames are dropped.

| Concern | Resolution |
|---------|------------|
| Removal speed | Unchanged. The single-delete path never raises the counter; only `_shake_delete_group` does. |
| Live UI freezes | None. Peers resume painting on the next event-loop tick after the final release. |
| Missed final-state paint | None. Every peer still receives a paint event after the flag is lowered; the motion engine settles to its real target on the next `_glide_tick`. |

**Lesson learned.** Per-node teardown compliance is necessary but not sufficient. Bulk-delete bursts need **scene-wide quiescence** for any per-frame mutator that could schedule a paint touching a peer endpoint. The `_bulk_removing` counter pattern is reusable anywhere a burst of `scene.removeItem()` calls can interleave with signal-driven repaints.

**Verification to perform:** repeat the 2026-04-17 test — open a 1200+ node session, trigger housekeeping with dozens of nodes shaking, confirm no `0xc0000005` in Event Viewer.

### 2026-04-18 — c0000409 in Qt6Core.dll: zombie-MarkdownNode signal-destructor race

**Symptom:** `c0000409` (`STATUS_STACK_BUFFER_OVERRUN`, Qt's `__fastfail` for invariant violations) in `Qt6Core.dll`, not `Qt6Widgets.dll`. Caught via Windows Event Viewer at 2026-04-18 03:07:36, roughly 1 second after the last logged icon-load. The Python log had nothing — the crash was at the C++ Core layer before anything could be written.

**Discovered because:** the newly-added Memory submenu (see `Documents/Nodes/...`) lets the user click through ~40 entries rapidly. Each click spawns a MarkdownNode under the "zombie" pattern (split content into readable cells, defer `removeItem` to next event-loop tick). Rapid usage exposed a latent race the single-click cadence rarely tripped.

**Root cause — new class of crash.** Different layer and different mechanism from the 2026-04-17 peer-paint-during-burst class:

- `Qt6Core.dll` (not Widgets) points to QObject / signal-slot / QTimer machinery, not paint.
- `c0000409` fastfail fires when Qt's C++ destructor begins `disconnect()`'ing signals *while an emission is still in flight targeting the same object.*
- MarkdownNode has live QObject machinery — a 100 ms `_delivery_timer` firing into `_check_render_delivery`, plus a background render thread — that keeps running between the synchronous `_split_into_nodes()` and the deferred `scene.removeItem(node)`.
- When the 100ms timer fires into the soon-to-die node at the same event-loop tick the deferred `removeItem` dispatches, the QObject destructor and the signal emission collide → fastfail.

**Why per-node `_prepare_for_removal` doesn't prevent this.** `_prepare_for_removal` is correct and cleans up properly — but it only runs *during* `removeItem`, not before it. The race lives in the **window between split-returning and removeItem-dispatching**, during which `_prepare_for_removal` hasn't run yet.

**Fix applied (synchronous machinery-quietening, scene-graph-preserving):**

This is the same pattern GitNode Phase 3 (2026-04-16) landed on: neutralise dangerous QObject-level machinery *synchronously* before the deferred window, but leave scene-graph children (proxy, buttons, ports) intact so Qt's own `removeItem` can tear them down cleanly.

| File:line | Change |
|-----------|--------|
| `nodes/MarkdownNode.py` | Added new method `_quiet_background_machinery()` — stops `_delivery_timer`, disconnects its `timeout` signal, and sets `_removed = True` to signal the worker thread to bail. Does not touch `_html_proxy`, `_editor`, or buttons. |
| `main_window.py::_spawn_doc` (Info sidebar zombie path) | Calls `node._quiet_background_machinery()` after `_split_into_nodes()` and before the deferred `removeItem`. The full `_prepare_for_removal` still fires naturally via `itemChange` when `removeItem` reaches the node, and its idempotent handling of already-stopped timers means no double-disconnect issues. |

The button-driven `_split_into_nodes` call on a live MarkdownNode is unaffected — only the zombie-spawn caller in the Info sidebar quiets the machinery, because only that caller disposes the node afterward.

**Pattern takeaway — pairs with the peer-paint fix.** The two 2026-04 crash classes live at different Qt layers and need different fix shapes:

- **Peer-paint-during-burst** (`0xc0000005` in Qt6Widgets.dll) — a paint event on a freed widget during bulk removal. Fix: scene-wide `_bulk_removing` quiescence counter + endpoint-validity guards on cross-node references.
- **Signal-destructor race** (`c0000409` in Qt6Core.dll) — a signal emission in flight when a QObject destructor calls `disconnect()`. Fix: quiet the signal/timer machinery synchronously before any deferred removeItem window.

Both are bounded cases of the same underlying principle: *any deferred-removal pattern must close all inflight-signal windows before the deferral, not during it.*

### 2026-04-18 — ClaudeNode inner-widget signal-destructor race

**Symptom.** `0xc0000409` (STATUS_STACK_BUFFER_OVERRUN, Qt fastfail) in `ucrtbase.dll` at 20:33:58, two seconds after `_prepare_for_removal complete` logged for a shake-deleted ClaudeNode at 20:33:56. All five crew phases ran cleanly — the crash was purely on the Qt side, after Python teardown appeared successful.

**Root cause.** The ClaudeNode's inner `_input` widget (`_InputEdit`, a `QTextEdit` subclass) has three signal connections wired to bound methods on the node itself:

```
self._input.submitted.connect(self._send_input)
self._input.textChanged.connect(self._on_input_changed)
self._input.focused.connect(self._on_input_focused)  # via QTimer.singleShot(0, ...)
```

The demolition crew's proxy teardown for `_input_proxy` sets the proxy's widget to None, severs the proxy, and `deleteLater()`s the inner widget — standard canonical recipe. But `deleteLater()` schedules C++ deletion for the next event-loop tick. Between `deleteLater()` and actual destruction, the widget still holds its signal connections to bound methods on `self`. If any of those signals fire during that window — a late `focused` emission from focus change triggered by the teardown itself, a `textChanged` from Qt's internal cleanup, a `submitted` from a late keystroke queued before teardown began — the slot invokes a bound method on a node mid-destruction. Destructor collides with emission → fastfail.

Same class as the MarkdownNode fix from earlier today: deferred Qt deletion + signals connected to soon-to-die targets = race window. Different node, different signals, identical failure mode.

**Fix applied to `nodes/ClaudeNode.py::_demolition_pre`:**

| Step | What | Why |
|------|------|-----|
| 1 | Disconnect `_input.submitted` → `_send_input` | Before proxy teardown schedules widget deletion |
| 2 | Disconnect `_input.textChanged` → `_on_input_changed` | Same |
| 3 | Disconnect `_input.focused` → `_on_input_focused` | Same; this one especially because focus events can fire during teardown |

Each guarded with `try/except (RuntimeError, TypeError)` for idempotence — safe to run multiple times, safe if the connection was never actually made.

**Sweep — MergeNode._list.customContextMenuRequested.** Same pattern scanned for, found one more: `MergeNode._list` (a `QListWidget` inside `_list_proxy`) had an unaddressed `customContextMenuRequested → _list_context_menu` connection. Low-probability because it only fires on right-click, but added to `MergeNode._demolition_pre` as cheap insurance.

**Rule generalised for future nodes.** Any signal connection `self._inner_widget.signal.connect(self._bound_method)` where `_inner_widget` lives inside a proxy listed in `_demolition_proxies` must be explicitly disconnected in `_demolition_pre`. The crew's proxy teardown handles the widget's deletion but cannot infer which signals were connected to bound methods on the host node. When adding a new node that wires inner-widget signals, extend `_demolition_pre` with the matching disconnects.

**Checklist addition:** audit new nodes for `self._<inner>.<signal>.connect(self.<method>)` patterns. If the inner widget is proxied, the signal must be severed before the crew's walk.

### 2026-04-18 — Demolition crew extraction (architectural refactor)

**Context.** By this date the node teardown procedure had evolved into an official five-phase procedure documented above with detailed ordering rules, recurring recipes (proxy-widget teardown, timer stop+disconnect, thread bail, media-player sever), and an ever-expanding list of class-of-crash lessons. Every node carried the procedure in its own `_prepare_for_removal` override — and every new node had to re-learn the same recipes. Construction workers were carrying dynamite in their toolboxes.

**Refactor — Carpenters leave labels; demolition crew reads them.**

The teardown procedure is now a dedicated `nodes/_demolition.py` module — a standalone crew that arrives when a node leaves the scene, reads the node's declarative manifest of what to come down, runs the canonical sequence, and leaves. Nodes declare what they own; the crew handles the choreography.

**Declarative manifest (class attributes, all optional):**

| Attribute | Shape | Purpose |
|-----------|-------|---------|
| `_demolition_proxies` | `list[str]` — attr names | QGraphicsProxyWidget teardown (setWidget(None) → inner setParent(None)+deleteLater() → removeItem → null, plus scene-rect invalidate) |
| `_demolition_timers` | `list[(attr, slot_name)]` | QTimer.stop() + timeout.disconnect(slot) |
| `_demolition_animations` | `list[(attr, [signal_names])]` | QVariantAnimation.stop() + disconnect of each named signal |
| `_demolition_thread_flag` | `str` — attr name | Set attribute to `True` FIRST so background worker bails before any Qt teardown |
| `_demolition_media_players` | `list[str]` | QMediaPlayer.stop() + setVideoOutput(None) + setAudioOutput(None) + deleteLater() |
| `_demolition_workers` | `list[(attr, [signal_names])]` | Disconnect each named signal on a worker object |

**Optional hooks for bespoke work:**

- `_demolition_pre(self)` — runs FIRST, before the crew's standard sequence. For work that needs synchronous ordering before any other teardown (e.g. GitNode dismissing its loading plushie, VideoNode's deferred media chain, StickerNode's viewport tracking).
- `_demolition_post(self)` — runs LAST, after the standard sequence. Rarely needed.

**Manifest inheritance.** The crew's `_manifest(node, attr_name)` walks the full MRO and appends entries in declaration order, deduping on attr name. BaseNode declares universal items (`_shelf_anim`, `_update_throttle_timer`) once; every subclass inherits them automatically and adds its own on top. No node has to remember the universal set.

**Entry points.**

- BaseNode subclasses: `BaseNode._prepare_for_removal()` is now a one-line wrapper — `demolish(self)`. The existing Qt contract (called from `itemChange` on `ItemSceneChange`) is unchanged.
- Non-BaseNode roots (StickerNode): `itemChange` calls `demolish(self)` directly. The crew tolerates missing attributes (`connections`, `behaviour`, `_buttons`, `input_ports`, `output_ports`) and flows through the parts of the standard sequence that apply.

**Files touched:** 1 new (`nodes/_demolition.py`), 29 migrated (every node with a prior `_prepare_for_removal` override). Net: ~400 lines of boilerplate replaced with ~30 lines of declaration.

**Verification.** Every node type instantiated + torn down cleanly in the end-to-end smoke test. AST parse-check of all node files passes. No behavioural change intended — the crew's standard sequence preserves the phase-by-phase ordering and every previously-documented crash-class fix (the 2026-04-16 proxy audit, the 2026-04-17 peer-paint sweep, the 2026-04-18 StickerNode root-split, the 2026-04-18 PaletteNode rasterisation fix) is now baked into the crew's default procedure rather than repeated per node.

**Retrospective on the ordering story.**

The audit pass that preceded the refactor catalogued every node's `_prepare_for_removal`. The pattern had stabilised years ago: bespoke cleanup first, `super()` last. The crew's split between `_demolition_pre` and `_demolition_post` codifies this: the pre-hook is the "bespoke first" story, the standard sequence is the `super()` story, the post-hook is for the rare trailing work. No node needed a contortion to migrate — the shapes all slotted into the two hooks or the manifest categories cleanly.

The one category that genuinely stays per-node-inline is **peer signals targeted at bespoke slot methods** (PremiereBridgeNode's five transport signals, MergeNode's dynamic per-audio-node mediaStatusChanged, ClaudeNode's settings.watcher). These targets are bound to slot methods on self; the generic `disconnect()` on a worker in the manifest wouldn't discriminate. These each stay in `_demolition_pre` as inline disconnects. That's honest complexity, not boilerplate.

**Adding a new node type — the onboarding story.**

Before: "override `_prepare_for_removal`, copy from a reference implementation, audit against this compliance document, manually remember all five phases."

After: "declare what you own. Add `_demolition_pre` only if you have genuinely bespoke ordering."

The compliance document still matters — it's the reference for what the crew *does*, and the source of truth for what new crash-classes look like. But the individual node author no longer has to internalise it to ship a correct node.

### 2026-04-18 — PaletteNode shake-delete rendering artefacts

**Symptom.** Shake-deleting a PaletteNode left visible rasterised residue on the canvas for a frame or two — swatch-row pixels / border outline remnants in the area the node had occupied. No crash, no Event Viewer entry; the Python teardown log showed all five phases + `_prepare_for_removal complete` firing cleanly at 13:52:13.

**Root cause.** PaletteNode hosts two `QGraphicsProxyWidget` children (`_title_proxy` for inline title editing, `_palette_proxy` for the scrollable swatch grid). The palette body is a deeply nested `_PaletteWidget` with a `QScrollArea` containing a grid of `_SwatchCell` widgets, each using `QFrame.setStyleSheet(background: <hex>)` for its swatch — Qt paints those through stylesheet backing stores that sit outside the QGraphicsScene paint pipeline.

Two things compounded:

1. **Teardown order was inverted** from the PrettyEdit recipe (`setWidget(None)` → widget detach + `deleteLater()` → `scene.removeItem(proxy)`). PaletteNode did `scene.removeItem(proxy)` first, then `setWidget(None)`. Both orderings "work" — no crash — but the PrettyEdit order gives Qt a cleaner sequence for tearing down backing stores.
2. **No explicit `scene.invalidate()` of the proxies' former geometry.** `BaseNode`'s phase 0 invalidate covers the node's `boundingRect`, which geometrically contains the proxies. But for nested widgets backed by stylesheet pixmaps, `boundingRect` invalidation alone does not always reach the proxy's own cached pixels on the viewport buffer. Under the particle-storm load of shake-delete (8000 particles painting every frame), the stale pixels could persist for 1-3 frames.

**Fix applied to `nodes/PaletteNode.py::_prepare_for_removal`:**

| Step | What | Why |
|------|------|-----|
| 1 | Snapshot each proxy's `sceneBoundingRect()` *before* teardown | Need those rects after the proxies are gone |
| 2 | `proxy.setWidget(None)` | Sever C++ ownership first |
| 3 | `widget.setParent(None)` + `widget.deleteLater()` on inner widgets | Detach and schedule clean C++ deletion |
| 4 | `scene.removeItem(proxy)` | Pull proxy out of scene graph |
| 5 | `proxy = None` | Clear Python reference |
| 6 | `scene.invalidate(snapped_rect)` for each former proxy geometry | Force viewport repaint of those specific regions |
| 7 | `super()._prepare_for_removal()` | BaseNode's phase 0 invalidate still runs as a second belt-and-braces sweep |

**Lesson.** Any node hosting a QGraphicsProxyWidget whose inner widget tree renders via stylesheet backing stores (i.e. not pure QPainter operations) should invalidate the proxy's scene rect explicitly on teardown. The boundingRect-only invalidate that handles simple QPainter-painted nodes is necessary but not sufficient here.

**Secondary audit candidates** (same shape, not yet verified):

- `TreeNode._toolbar_proxy` — toolbar widget with buttons; may or may not produce visible residue on shake
- `MergeNode._list_proxy` — `QListWidget` with styled items; potentially similar

Both use the same "removeItem before setWidget(None)" order without explicit rect invalidation. Worth sweeping if artefacts show up.

### 2026-04-18 — StickerNode detached from BaseNode (root-split refactor)

**Context.** StickerNode previously inherited from BaseNode and overrode just enough to suppress the chrome — `_build_buttons` → `pass`, `_create_ports` → empty lists, `paint()` → skip chrome, `setBrush` → force `Qt.NoBrush` (to silence `NodeBehaviour.bg_anim`). This shape created a small paradox: every new feature on BaseNode had to be checked against "does the sticker want this, if not, what's the silencing pattern?" — a permanent tax for a node that conceptually has nothing in common with BaseNode except "lives on the canvas." The `setBrush` guard and the per-sticker `NodeBehaviour` cost both existed only because of the inheritance.

**Refactor.** StickerNode now inherits directly from `QGraphicsRectItem`. It is a first-class root type, sibling to BaseNode, designed as the reference implementation for future raw-image-style nodes (postcards, patches, cut-outs) that share the chromeless-alpha-PNG pattern without wanting the structural-node apparatus. ValueNode is a candidate for the next migration to this root — it is the second chromeless node already in the tree.

**Files changed:**

| File | Change |
|------|--------|
| `nodes/_shake_detect.py` | **New.** Shared shake-detect helper: `ShakeDetector` class + module-level `arm_cooldown()` / `is_cooling_down()`. Same threshold constants and reversal math as BaseNode's inline implementation. |
| `nodes/StickerNode.py` | Full rewrite. Inherits `QGraphicsRectItem` directly. Reimplements mouse-press/move/release, resize-at-corner, shake-to-delete, viewport pinning, and the idempotent `_prepare_for_removal` contract. Composes a `ShakeDetector`. Alpha click-through invariants documented in the class docstring. |
| `nodes/BaseNode.py` | Cooldown state moved into the helper. `_shake_cooldown_until` / `_SHAKE_COOLDOWN_S` replaced with `_arm_shake_cooldown()` / `_shake_cooling_down()` imports. `_shake_detach`'s group filter now duck-types (`hasattr(item, 'connections')` + `hasattr(item, '_prepare_for_removal')`) so multi-select shake-delete includes both BaseNode variants and stickers. |
| `graphics/Scene.py` | Session-save loop and scene-clear loop duck-type over node roots. BaseNode-specific teardown blocks (behaviour disconnect, timer stop) stay `isinstance(BaseNode)` — stickers correctly skip them. |
| `main_window.py` | `_select_chain` and `_autosave` has-nodes check duck-type. |
| `nodes/HealthNode.py` | GC census and scene-nodes counter now include both BaseNode and StickerNode — observability still accurate. |
| `nodes/ClaudeNode.py`, `nodes/ReadmeNode.py`, `nodes/TextNode.py`, `utils/placement.py` | Collision-avoidance `_clear()` helpers duck-type over node roots so fresh nodes don't spawn on top of stickers. |
| `Documents/Nodes/The Stickers Node.md` | Full writeup: alpha click-through as a feature with its three invariants, the pinning mechanism, the detach rationale. |

**Behavioural deltas (verified via AST parse + import smoke test):**

- `isinstance(sticker, BaseNode)` → `False`. This breaks exactly three code paths in the app, all intentionally updated above. Nothing else in the codebase grepped positive for a BaseNode-inheritance assumption against stickers.
- Session round-trip: `StickerNode() → to_dict() → from_dict() → uuid match` confirmed.
- `viewTransformed` signal on `IntricateView` confirmed present; StickerNode subscribes as primary pin channel, scrollbars kept as backup.
- Shake cooldown is now module-level in `_shake_detect` and shared by both roots — physical feel of shake unchanged.

**Wins:**

1. **Paradox removed.** StickerNode no longer needs a `setBrush` guard, because nothing is trying to paint over it on hover. No `NodeBehaviour` to silence; no `_show_emoji_btn = False` class flag; no `_build_buttons → pass`. The silencing layer is gone because the inherited surface it was silencing is gone.
2. **Zero per-sticker timer/animation tax.** No pulse timer, no bg animation, no signal connections beyond pin tracking. A 100-sticker canvas idles at canvas baseline.
3. **Click-through feature permanently documented.** `Documents/Nodes/The Stickers Node.md` + class docstring + `paint()` inline comment all declare the invariants: no background fill, tight-to-pixmap rect, alpha-preserving paint pipeline.
4. **Shake-detect logic now shared.** `ShakeDetector` is a 90-line helper usable by any future node root that wants the signature Intricate shake-delete gesture.

**Risks observed:**

- **Multi-shake with mixed selection.** If a user shakes a BaseNode with stickers selected, BaseNode's `_shake_delete_group` now includes the stickers via the duck-typed filter and purges them correctly. If a user shakes a sticker with BaseNodes selected, the sticker's `_on_shake_triggered` only deletes itself — it does not trigger a group purge. Single-shake-deletes-many-selected only works when the shake initiator is a BaseNode. Acceptable first-pass limitation; logged here for future symmetry pass.
- **Duck-type drift.** Six sites now duck-type on `hasattr(item, 'data') and hasattr(item, 'to_dict')` instead of `isinstance(BaseNode)`. Looser. If any unrelated scene item grows a `to_dict` method, it would get picked up. No such items exist today.

**Checklist addition:** when adding a new node root type (sibling to BaseNode and StickerNode), audit the six duck-typed sites to confirm they still mean what you want them to mean. They are: `graphics/Scene.py` (2: save loop, clear-all loop), `main_window.py` (2: `_select_chain`, `_autosave`), `nodes/HealthNode.py` (1 tuple), and the four collision-check `_clear()` helpers (`ClaudeNode`, `ReadmeNode`, `TextNode`, `utils/placement.py`).

### 2026-04-18 — StickerNode scrollbar signal-destructor race + GitNode ghost

**Symptom A (crash):** `0xc0000409` (STATUS_STACK_BUFFER_OVERRUN, Qt fastfail) in `ucrtbase.dll` while shake-deleting a pinned StickerNode. Log shows StickerNode `_prepare_for_removal` logged phases 1–5 at 12:12:52, but the `_prepare_for_removal complete` line never fired — the process died between phase 5 and the tail return. Same fastfail family as the 2026-04-18 MarkdownNode fix, but triggered through a different per-frame signal.

**Symptom B (ghost):** Shortly before the crash, a shake-deleted GitNode stayed rendered on the canvas for ~5 seconds after `_prepare_for_removal complete` logged cleanly, then vanished. No Python error, no Event Viewer entry — a pure repaint lag.

**Root cause A — StickerNode scrollbar signals.** `StickerNode._activate_pin()` connects to both `view.horizontalScrollBar().valueChanged` and `verticalScrollBar().valueChanged`, routing scroll events into `_on_viewport_changed` → `self.setPos()`. These are per-frame signals owned by the view, not the node, so `NodeBehaviour.disconnect_all()` does not touch them. Disconnect happens inside `_prepare_for_removal`, which runs *during* `removeItem` — not before it. If a scrollbar tick fires in the window between `_shake_delete` setting `_pending_shake_delete = True` and the deferred `removeItem` firing, the signal emission collides with the forming destruction path → fastfail. StickerNode had never been listed in this compliance log — first audit.

**Root cause B — deferred-remove starvation.** `QTimer.singleShot(0, removeItem)` fires on the next event-loop tick. An 8000-particle `sprinkle()` burst saturates paint events, delaying that tick by seconds on a busy canvas. Meanwhile, the scene's painted buffer still shows the node (its `QGraphicsItem` is still in the scene graph until `removeItem` fires), producing the "visible but unclickable" ghost. `setFlags(0)` zeros interaction but does nothing for rendering.

**Fix A+B applied (three parts):**

**1. Synchronous shake-time quieting** (`nodes/BaseNode.py`).
New hook `BaseNode._quiet_for_shake()` — no-op on base, overridden per node type. Called from both `_shake_delete` (on self) and `_shake_delete_group` (on self and every doomed other) *before* any deferred `removeItem` is scheduled. Pairs with the MarkdownNode zombie-path pattern but generalised so any node type with peer-level signals can opt in without caller-side coupling.

**2. StickerNode override** (`nodes/StickerNode.py`).
- `_quiet_for_shake()` synchronously calls `_disconnect_viewport_tracking()` — severs both scrollbar signals before the deferred window opens.
- `_on_viewport_changed()` gains three guards: `shiboken6.isValid(self)`, `scene._bulk_removing > 0` early-return, and `self._removal_done` early-return. Any scrollbar tick that slips through the disconnect still can't mutate a dying node.

**3. Scene-rect invalidation on deferred remove** (`nodes/BaseNode.py`).
Both the single-node `_deferred_remove` (in `mouseReleaseEvent`) and the group `_deferred` callback capture `node.mapRectToScene(node.boundingRect())` *before* deferring, then call `scene.invalidate(rect)` after `removeItem()`. The invalidate is cheap and forces the viewport to repaint the ghost region on the next paint pass, eliminating the multi-second linger even under heavy particle load.

| Concern | Resolution |
|---------|------------|
| Removal speed | Unchanged. Quieting is a local disconnect, invalidate is a rect push. |
| Live UI freezes | None. Invalidate is async — Qt batches it with the next paint. |
| Missed final-state paint | None. The invalidate triggers one guaranteed repaint of the ghost region. |
| Unpinned StickerNodes | `_disconnect_viewport_tracking` early-returns if `_pin_connected` is False, so the hook is free for the common case. |

**Pattern takeaway.** Adds a fourth class to the ledger:

- **Peer-paint-during-burst** (`0xc0000005`, Qt6Widgets.dll) → scene-wide `_bulk_removing` counter + endpoint guards.
- **Signal-destructor race** (`c0000409`, Qt6Core.dll / ucrtbase.dll) → quiet signals synchronously before the deferred window.
- **Cross-thread QTimer.singleShot drops** → main-thread flag polling.
- **Deferred-remove starvation ghost** (no crash, visible residue) → capture scene rect before deferral, `scene.invalidate()` inside the deferred callback.

**Checklist addition:** any node type that connects to **view-level** or **scene-level** signals (scrollbars, `scene.changed`, etc., as opposed to node-local timers/animations) must override `_quiet_for_shake()` to disconnect them synchronously. Relying on `_prepare_for_removal` alone is insufficient — that hook runs inside `removeItem`, not before it.

**Verification to perform:** pin a StickerNode, shake-delete it while scrolling the canvas. Confirm no fastfail in Event Viewer, no ghost on the viewport, `_prepare_for_removal complete` appears in the log.

### 2026-04-17 — Second-pass audit: peer-paint-during-burst sweep

After the primary fix landed, a codebase-wide second pass was done to find **secondary and tertiary instances of the same pattern** — any per-frame mutator that could schedule a peer repaint during a bulk removal, or any paint routine that dereferences a `QGraphicsItem` it does not own.

**Tier 1 fixes applied (same root cause, different site):**

| File:line | Issue | Fix |
|-----------|-------|-----|
| `graphics/Scene.py::_clear_all` | Session reload / scene reset is a bulk-removal burst identical in shape to `_shake_delete_group`, but with no quiescence counter raised around it. A concurrent pulse/bg/glide tick could crash it the same way. | Raise `self._bulk_removing` at the top of `_clear_all`, release via double-deferred `QTimer.singleShot(0, ...)` after the final `removeItem`. |
| `nodes/NodeBehaviour.py::pulse_anim.valueChanged` | Directly wired to `self._node.setScale` (C++ slot). `setScale()` invalidates the peer's paint region every pulse frame — another vector that could land a paint mid-burst. | Route through new `_on_pulse_value` method that early-returns if `node.scene()._bulk_removing > 0`. Disconnect path updated to match. |

**Tier 2 fixes applied (2026-04-17, follow-up pass):**

| File:line | Issue | Fix |
|-----------|-------|-----|
| `nodes/NodeButton.py::_reset` | `_reset_timer` survives if `detach()` isn't called (e.g. exception earlier in `_prepare_for_removal`). A late tick could `self.update()` on a dead peer. | Early-return if `scene()` is None or `scene._bulk_removing > 0`. Trivial cost in common path. |
| `main_window.py::closeEvent` (opacity-zero branch) | `_joy_timer`, `_happy_timer`, `_glow_timer` are parented to the window but could fire between `event.accept()` and C++ destruction, touching half-torn UI state. | Explicit stop + disconnect loop for all three in the final close branch before `event.accept()`. Each is guarded with `hasattr` so conditionally-created timers (like `_glow_timer`) don't NPE.

**Tier 3 (already safe — confirmed, no change):**

- `graphics/Particles.py` `_tick_timer` — `_FadingParticle._update()` already catches `RuntimeError` on dead scene/item access and self-kills. Uses `flush_scene` before any bulk removal. This is the reference implementation for other per-frame mutators.
- `nodes/Port.py` — no timers, no animations.
- `nodes/NodeButton.py::EmojiButton` — no timer or signal into the node graph.

**Pattern takeaway for future node types:** any new per-frame mutator (timer or animation valueChanged) whose slot schedules a paint must route through a gate that checks `node.scene()._bulk_removing`. Direct C++ slot connections (like `anim.valueChanged.connect(node.setScale)`) cannot be gated — they must go through a Python wrapper. The checklist above was updated to make this a required audit item.

### 2026-04-16 — Codebase-wide proxy + timer audit

**Scope:** Full audit of all 41 node files, `main_window.py`, `graphics/Scene.py`, `graphics/Connection.py`, `widgets/`, `utils/`, and the Pretty Widgets package.

**Fixes applied in bulk commit `a113410`:**

| File | Issue | Fix |
|------|-------|-----|
| BloomNode.py | `proxy.setWidget(None)` without `scene.removeItem(proxy)` | Added `scene.removeItem()` before detach |
| ClaudeNode.py | Same — two proxies (`_input_proxy`, `_body_proxy`) | Added `scene.removeItem()` for both |
| MergeNode.py | Same — `_list_proxy` | Added `scene.removeItem()` |
| PaletteNode.py | Same — `_title_proxy`, `_palette_proxy` | Added `scene.removeItem()` for both |
| SequenceNode.py | Same — `_slider_proxy` | Added `scene.removeItem()` |
| TextNode.py | Same — `_html_proxy` | Added `scene.removeItem()` |
| TreeNode.py | Same — `_toolbar_proxy` | Added `scene.removeItem()` |
| ValueNode.py | Same — `_slider_proxy` | Added `scene.removeItem()` |
| Scene.py (×2 paths) | `_glide_timer.stop()` without `.disconnect()` | Added `timeout.disconnect(_glide_tick)` |
| main_window.py | `_tooltip_timer = QTimer()` without parent | Changed to `QTimer(self)` + disconnect on cancel |

---

## Post-Refactor Sanity Checklist

After large-scale edits to shared widgets or node code — especially when extracting helpers to module level or moving methods between classes — run through this checklist before committing:

- [ ] **AST method count** — `python -c "import ast; ..."` to confirm the class has the expected number of methods. Methods silently swallowed by a module-level function won't raise a syntax error.
- [ ] **Module-level function boundaries** — any function at column 0 that appears mid-file will capture all subsequent indented code as nested functions. Verify nothing follows it at the wrong indent level.
- [ ] **"Continued class" comments** — Python does not support resuming a class body. If you see `# (continued)` after a module-level def, the code below it is *not* in the class. Restructure immediately.
- [ ] **`hasattr` spot-check** — for any method called in teardown paths (`_prepare_for_removal`, `teardown`, `disconnect_all`), verify with `hasattr(ClassName, 'method_name')` that it actually resolves at runtime.
- [ ] **crash.txt review** — check `logs/crash.txt` after testing deletions. A ghost node (rendered but unclickable) is the telltale sign of a teardown exception that was swallowed by the deferred removal's `try/except`.

---

## Checklist for Future Node Types

When adding a new node type or auditing an existing one, walk through this checklist:

- [ ] Does the node create any `QTimer`? → stop + disconnect in `_prepare_for_removal()`
- [ ] Does the node create any `QVariantAnimation`? → stop + disconnect in `_prepare_for_removal()`
- [ ] Does the node embed a `QGraphicsProxyWidget`? → detach widget, reparent, `deleteLater()`, `scene.removeItem()`
- [ ] Does the node spawn background threads? → add a cancellation flag, set it before any Qt teardown
- [ ] Does the node connect to any signals not covered by `BaseNode`? → disconnect in `_prepare_for_removal()`
- [ ] Does `_prepare_for_removal()` call `super()` as its **last** line? → must always be last
- [ ] Does the node programmatically remove other nodes? → never call `_prepare_for_removal()` explicitly; only neutralize dangerous C++ objects (stop players, sever media links), then defer `removeItem` and let `itemChange` handle teardown
- [ ] Does the node use cross-thread callbacks? → never use `QTimer.singleShot` from worker threads; use flags polled by a main-thread timer instead
- [ ] Does the node own any per-frame mutator that schedules a paint on a **peer** (not just itself)? → early-return when `node.scene()._bulk_removing > 0`. Scene-level quiescence is the bulk-delete safety net.
- [ ] Does any paint/glide routine dereference a `QGraphicsItem` it does not own (e.g. a wire reading its endpoint node)? → guard with `shiboken6.isValid(x)` + `x.scene() is not None` before every dereference inside paint / timer ticks.

## Guard: `_removal_done`

`BaseNode._removal_done` (added 2026-04-16) prevents `_prepare_for_removal()` from running twice. It is set to `True` at the top of `_prepare_for_removal()` and checked in `itemChange` before calling it. This makes teardown idempotent — safe for paths where a node is neutralized before the deferred `removeItem` fires.
