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
