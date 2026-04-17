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

### 2026-04-17 — Second-pass audit: peer-paint-during-burst sweep

After the primary fix landed, a codebase-wide second pass was done to find **secondary and tertiary instances of the same pattern** — any per-frame mutator that could schedule a peer repaint during a bulk removal, or any paint routine that dereferences a `QGraphicsItem` it does not own.

**Tier 1 fixes applied (same root cause, different site):**

| File:line | Issue | Fix |
|-----------|-------|-----|
| `graphics/Scene.py::_clear_all` | Session reload / scene reset is a bulk-removal burst identical in shape to `_shake_delete_group`, but with no quiescence counter raised around it. A concurrent pulse/bg/glide tick could crash it the same way. | Raise `self._bulk_removing` at the top of `_clear_all`, release via double-deferred `QTimer.singleShot(0, ...)` after the final `removeItem`. |
| `nodes/NodeBehaviour.py::pulse_anim.valueChanged` | Directly wired to `self._node.setScale` (C++ slot). `setScale()` invalidates the peer's paint region every pulse frame — another vector that could land a paint mid-burst. | Route through new `_on_pulse_value` method that early-returns if `node.scene()._bulk_removing > 0`. Disconnect path updated to match. |

**Tier 2 findings (latent, lower priority — not fixed in this pass):**

- `nodes/NodeButton.py` `_reset_timer` (line 64–67) — survives if `detach()` isn't called. Defensive `_bulk_removing` check inside `_reset()` would harden it. Low risk today because `detach()` is reliably called from `_detach_buttons()` in `_prepare_for_removal`.
- `main_window.py` `_joy_timer`, `_happy_timer`, `_glow_timer` — UI-only, don't touch the scene graph. Not a crash risk for the current pattern; noted for future shutdown-ordering work.

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
