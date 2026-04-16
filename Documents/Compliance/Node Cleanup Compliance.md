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

## Guard: `_removal_done`

`BaseNode._removal_done` (added 2026-04-16) prevents `_prepare_for_removal()` from running twice. It is set to `True` at the top of `_prepare_for_removal()` and checked in `itemChange` before calling it. This makes teardown idempotent — safe for paths where a node is neutralized before the deferred `removeItem` fires.
