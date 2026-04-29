# The Warm Node

The main content node — the star of the show, the seed Intricate grew from. A panel with an emoji accent, an editable title, and a body of free-form text. Drop a thought into a WarmNode, drag the corner to resize, paste a paragraph and watch it auto-fit, paste a wall of text and watch it chain-split into one node per paragraph. WarmNode is where the bulk of the user's writing lives, and most of the platform conventions every later node type inherited started here.

If StickerNode is "an image on the canvas", AboutNode is "a label on the canvas", and ValueNode is "a dial on the canvas", WarmNode is "a thought on the canvas". The whole canvas exists to be a non-linear arrangement of WarmNodes; everything else is supporting cast.

## Core Files

| File | Purpose |
|---|---|
| `nodes/WarmNode.py` | The node — paint, lazy editor, paste-split, bridge to The Majestic, scene-embedded context menu |
| `data/WarmNodeData.py` | Pure Python dataclass — `title`, `body_text`, `emoji`, geometry |

## How It Works

### Three Ways to Create

1. **Sidebar button** — click the warm icon; spawns a fresh empty WarmNode at the canvas centre with default size
2. **Paste-split chain spawn** — pasting multi-paragraph text into an existing WarmNode triggers `_split_oversized_paste`, which keeps the first paragraph in the originating node and chain-spawns one WarmNode per remaining paragraph, wired together with Connection lines so the original reading order is preserved spatially
3. **Session restore** — `from_dict` rebuilds the data; the body paints directly from `data.body_text` without ever building an editor

### Layout

Top to bottom:

```
┌─────────────────────────────────┐
│ ☕ Title                        │   ← emoji + title row
│                                 │
│ Body text wraps here, painted  │   ← body zone (lazy editor)
│ directly from data.body_text    │
│ when no editor is active...     │
└─────────────────────────────────┘
```

Layout constants live at module top (`EMOJI_SIZE`, `TITLE_HEIGHT`, `PADDING`, `BODY_TOP`). The emoji is painted as an accent by BaseNode; the title is painted by BaseNode; the body is painted by WarmNode itself in `paint_content`, after `super().paint_content(painter)` handles the emoji and title.

### The Lazy Editor — One Active at a Time

A WarmNode does **not** own a `PrettyEdit` from construction. The editor is built on the first edit-trigger and reused for the lifetime of the node. In a 1200-node session this is the difference between 1200 eager `PrettyEdit` constructions on session load (each one a `QGraphicsProxyWidget` with a `QTextDocument` inside) and ~zero — the editor is only built for nodes the user actually clicks.

This is the **single most important performance contract** for WarmNode. A populated session loads in ~36ms because nothing in WarmNode's `__init__` builds Qt widgets — only the dataclass and the bridge timer scaffolding. The cost of full editor construction is amortised across the user's actual editing sessions, not paid up-front for nodes they may never touch this session.

`paint_content` paints the body directly from `data.body_text` when the editor is absent or its proxy is hidden. When the editor's proxy is visible, the painter exits early and lets the editor render itself.

### Single-Click to Edit (Body)

Single-click in the body zone activates the inline editor. Previously this was double-click, when every WarmNode owned a live `PrettyEdit` from construction — double-click was the "focus this one, since they're all already loaded" gesture. After the lazy refactor (2026-04) single-click became the right cost profile: clicking the node *is* the request to edit it.

The implementation walks Qt's click-vs-drag distinction:

- `mousePressEvent` arms a single-click gesture if the click is unmodified left-button in the body zone, recording the press position
- `mouseReleaseEvent` checks the release position; if within a 4-px radius of the press, treat as click and launch the editor; if outside, Qt has already moved the node as a drag and we just defer to `super()`

Shift/Ctrl clicks fall through to Qt's default selection semantics. The 4-px squared threshold (16 px²) is tighter than Qt's default drag distance so tiny drags don't get absorbed as clicks.

### Title Editing — Bridge to The Majestic

Double-clicking the title zone (or selecting "The Majestic" from the body's context menu) launches **Notepad++ Duplex+ Turbo** with a bidirectional JSON bridge. The bridge file lives at `Documents/Data/.warm_bridge_<uuid>.json`; both the running Intricate and the launched editor watch it.

**On launch:**

1. `_teardown_bridge()` cleans any stale bridge session
2. The bridge JSON is written with the current `title`, `body_text`, `node_uuid`, `writer="intricate"`, and a timestamp
3. Editor subprocess is launched with `--bridge <path>`. Resolution order for the editor binary: absolute or relative path → Desktop sibling scan (preferring source repos with `main.py` over frozen `.exe` builds) → `shutil.which()` PATH fallback. Path traversal characters are rejected.
4. A `QFileSystemWatcher` on the bridge file is connected with debounce timers (300ms read debounce, 500ms write debounce) so rapid typing doesn't thrash the watcher
5. Curtains roll up so the editor takes focus

**On editor write:** the watcher fires → debounce → `_process_bridge_change` reads the file. If the writer field says `"intricate"` it's an echo of our own write and gets ignored; otherwise body_text and title are applied to `data` and the canvas repaints. Auto-fit-height re-runs if the body changed.

**On Intricate edit:** `_on_text_changed` fires per keystroke → 500ms write debounce → `_write_bridge` writes the current state to the bridge file. The `_bridge_writing` flag is set during the write and cleared 150ms later; any watcher tick within that window is treated as our own echo and ignored.

**Crash detection:** a daemon thread watches the editor subprocess for early exit (within 2 seconds). If the editor crashes during launch, its stderr is logged so silent import errors become visible. After the 2-second window, stderr is closed to avoid blocking on the still-running process.

The bridge is a **per-WarmNode** session: every editing-paired WarmNode has its own bridge file. When the user closes the editor or the WarmNode is removed, `_teardown_bridge()` stops the watchers, disconnects the debounce signals, and removes the bridge file from disk.

### Paste-Split — Paragraph-Aware Chain Spawn

A paste containing paragraph breaks (`\n\n`) gets chain-spawned: one WarmNode per paragraph, wired together with Connection lines. The author of the text already did the cognitive work of separating thoughts; the canvas honours that separation spatially.

`_SmartPrettyEdit.insertFromMimeData` is the trigger:

```python
paragraph_count = text.count('\n\n') + 1 if text.strip() else 0
too_long = len(text) > self._split_threshold
should_split = paragraph_count > 1 or too_long
```

A single-paragraph paste goes in normally and the node's width-wrap handles it. Multi-paragraph or pathologically long single-paragraph (`> WARM_SPLIT_SAFETY_CEILING = 20_000`) triggers `_split_oversized_paste`:

1. The full content gets chunked via `utils/text_chunker.paragraph_chunks` (paragraph-aware, with the cascading chunker as fallback for paragraphs that still exceed the safety ceiling)
2. The first chunk replaces the originating node's body
3. Each subsequent chunk spawns a new WarmNode — auto-fit-height to the document, placed via `spiral_place` with `wander_origin(prev_node)` so the chain meanders organically rather than running in a straight line
4. Connections wire each new node to its predecessor in the chain
5. The InfoBar whispers the result: *"big paste split into N nodes"*

No cap on chain length — Intricate is optimised to load 1200+ nodes in ~36ms, so a thousand-paragraph paste is on-spec. The 2026-04-18 crash class (Qt6Core.dll fault when a single `QTextDocument` carries multi-megabyte content) is what motivated the safety ceiling; paragraph-split is the natural solution that also matches how a human reader thinks.

### Scene-Embedded Context Menu

Right-clicking the body opens a context menu that lives **inside the scene** as a `QGraphicsProxyWidget`, not as a top-level `Qt.Popup` window. The reason is the **Murfy sidekick wire**: `Connection.zValue = 9999`, and a top-level popup renders above every scene item regardless of Z. A scene-embedded proxy at `zValue=100` lets the wire render *over* the menu, which is the visual contract for the right-click-to-connect gesture.

The menu is built as a hand-rolled `QFrame` (`_SceneMenu`) with `QHBoxLayout` rows mirroring `PrettyMenu`'s look — gradient hover, primary border, Theme.backDrop background. The standard `QTextEdit` actions (Cut, Copy, Paste, Undo, Redo) get harvested from `createStandardContextMenu()` and pulled into the scene menu, with "The Majestic" prepended as the load-bearing entry.

Dismissal: action triggered, Escape, or click outside the proxy. A scene-level event filter (`_CtxClickFilter`) handles the outside-click and Escape paths.

### Paste-Time HTML Strip

The editor's paste handler strips HTML on insert. Web-paste with per-character span formatting made paint cost scale with run count and loaded the whole canvas (the 2026-04-18 lag investigation). Plain text from a span-heavy source becomes plain text in the document; if the user actually wants formatting, they're using the wrong tool.

Legacy sessions with HTML body_text still survive — `_html_to_plain` round-trips through a scratch `QTextDocument` to strip the tags cleanly on construction and on bridge reads. The `_on_text_changed` handler stores plain text only.

### Auto-Fit Height

Two modes:

- **Grow-only** (default) — expands the node when text overflows the current height; never reduces below the current setting. Preserves any manual corner-drag resize the user has applied, and preserves a user's custom height across session reloads.
- **Snug** (`shrink=True`) — both grows and shrinks so the node exactly matches its body text plus padding. Used by the markdown-split spawner so freshly-spawned chain nodes pack tightly against their content instead of carrying the default empty space at the bottom. Those nodes have never been resized manually, so shrinking is safe.

When the editor is active, height measurement runs through `editor.document().setTextWidth + size().height()` (most accurate — same layout Qt will render). When the editor is idle, measurement runs through `QFontMetrics.boundingRect` with word-wrap on a probe rect — identical to what `paint_content` renders, no editor construction required. Both paths share the class-level shared font cache (`_SHARED_BODY_FONTS`).

### Auto-Fit Title Width

`_auto_fit_title_width` grows (never shrinks) the node's width if the current title would overflow. Measured via `_measure_title_width` (QPainterPath.addText().boundingRect()) rather than QFontMetrics.horizontalAdvance — Chandler42's advance-table sidebearings over-report painted ink on this font and would inflate the auto-fit width. Same scoped swap documented in the auto-fit-measurement-contract memory.

## Data Class

`WarmNodeData` extends `NodeData` with:

- `title: str` — the title row text
- `body_text: str` — the body content (plain text only post-2026-04-18)
- `emoji: str` — emoji accent rendered top-left by BaseNode
- standard geometry — `x`, `y`, `width`, `height`, `uuid`, `node_type="warm"`, etc.

Default size: WarmNode's default rect is sized for a typical paragraph of body text plus the emoji + title row.

## Lifecycle

### Creation

`Scene.add_warm_node(pos)` → `WarmNode(WarmNodeData())`. The bridge timers (debounce, write-debounce) are scaffolded but not started; the watcher is `None` until `_launch_editor` runs.

### Removal

`_demolition_pre()`:

1. `_teardown_bridge()` — stops the file watcher, disconnects debounce signal connections, removes the bridge JSON from disk
2. If the editor was built, `self._editor.teardown()` handles the proxy-widget cleanup inside PrettyEdit itself
3. Nulls `self._editor`
4. Defers to BaseNode's standard sequence

If the editor was never built (the common idle case), step 2 short-circuits and the WarmNode tears down with just the bridge cleanup and the BaseNode contract.

## Technical Notes

- **The lazy-editor refactor** (2026-04) was the load-time breakthrough that made 1200-node sessions feel instant. It also forced the single-click activation gesture to make sense (the previous double-click made sense only when every node owned a live editor). The two changes are paired.
- **`WARM_SPLIT_SAFETY_CEILING = 20_000`** is the escape valve for a pathological single-paragraph wall — roughly 5–8 printed pages. Beyond that the cascading chunker fires regardless of paragraph structure. For natural prose paragraphs the ceiling is almost never hit; the safety net exists for raw log-dumps and JSON pastes.
- **Class-shared body font cache** (`_SHARED_BODY_FONTS`): all WarmNode idle bodies share one `QFont` + `QFontMetrics` pair. Same pattern AboutNode and TextNode use. Negligible memory cost, real paint-time savings on populated scenes.
- **`PADDING = 10.0`, `BODY_TOP = PADDING + EMOJI_SIZE + 16.0`** — these layout constants are deliberately at module top, not on the class, so a future TextNode-style descendant can override with different chrome without copying the whole BaseNode subclass scaffold.
- **The scene-embedded context menu** is a precedent for any future right-click menu in Intricate that needs to coexist with overlay items. The Murfy wire was the first overlay; the same Z-order discipline will apply to any future overlay (HUD, particle effect, debug overlay).
- **`focusOutEvent`** restores `view.setFocusPolicy(Qt.NoFocus)` when the node loses focus — the editor temporarily lifts it to `StrongFocus` during edit so keyboard input lands in the proxy. The lift/restore pattern is shared with AboutNode and ImageNode caption editing.
- **Bridge writes use in-place writes (`open(path, "w")` + `fsync`)**, never temp+replace. `os.replace` deletes+recreates on Windows which drops the path from `QFileSystemWatcher` — a known issue that also blocks future proxying through a networked file layer. The `_bridge_writing` flag carries the "ignore the next watcher tick" contract for the duration of our own write.
