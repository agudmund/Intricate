# The About Node

The sticky-note primitive. A small editable label that lives on the canvas next to whatever it's commenting on — a category memo, a section header, a quiet annotation hovering by a group of related nodes. Smaller than a WarmNode, no body area, no editor proxy in the idle state, just a single line of text painted directly into the rect with the option to expand into multiple lines when the user types past the first.

AboutNode is also the first adopter of the depth-toggle convention (paired `bg_color` / `bg_color_front` in Theme), the first home of the "shelf reveal via resize gesture" interaction (later lifted to VideoNode and others), and one of the **three notification channels** the app uses to whisper at the user — alongside ClaudeResponseNode and the InfoBar. Each channel has a distinct voice and each is deliberately not unified with the others.

## Core Files

| File | Purpose |
|---|---|
| `nodes/AboutNode.py` | The node — paint, lazy editor, auto-expand, shelf-via-resize gesture |
| `data/AboutNodeData.py` | Pure Python dataclass — `label`, `title`, depth-toggle state, geometry |

## How It Works

### Three Ways to Create

1. **Sidebar button** — click the about-node icon; spawns a fresh empty AboutNode at the canvas centre with default snug-fit dimensions
2. **Spawned by other nodes as a notification** — `ImageNode`, `VideoNode`, and `StickerNode` use AboutNode as their drift-warning surface (*"source drifted — cache no longer matches"*); WarmNode's caption AboutNode auto-spawns next to a freshly-loaded image. The spawning node sets the label and positions the AboutNode adjacent
3. **Session restore** — `from_dict` rebuilds the data, the node renders directly from `data.label` without ever building an editor

### Snug-Fit by Default

The constructor measures the label's font ascent, descent, and line spacing and seeds `data.height` and `data.width` so a fresh AboutNode lands in its correct proportions immediately:

```python
font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
font.setStyleName(self._TITLE_STYLE)
fm = QFontMetrics(font)
if data.height == 0.0:
    data.height = AboutNode._HIDDEN_TOP_OFFSET + fm.lineSpacing() + Theme.aboutHighlightTrim + 6
if data.width == 0.0:
    data.width = fm.horizontalAdvance(data.label or data.title) + 28
```

No yank-to-tighten ritual on every fresh AboutNode — defaults already fit. `_min_height` is set to zero so the user can shrink the rect freely below the text-holding floor; AboutNodes double as colour-indent stickers without text, and that use case needs the freedom to be tiny.

### Lazy Editor

The editor is a `PrettyEdit` proxy and it is **not** built on construction. `_build_editor` runs on the first edit-trigger; subsequent edits reuse the same instance. In a 1200-node session, that's the difference between 1200 eager `PrettyEdit` constructions on session load and ~zero — the editor is only built for nodes the user actually touches.

`paint_content` paints the label directly from `data.label` (or `data.title` as fallback) when the editor is absent or its proxy is hidden. When the editor's proxy is visible the painter exits early — the editor handles its own rendering.

### Auto-Expand While Typing

When the editor is active, `_auto_expand` fires on every `contentsChanged` signal. The document measures its natural unwrapped width via `setTextWidth(-1)` + `idealWidth()`, the rect grows to match, and the editor proxy repositions:

```python
new_w = max(self._min_width,  doc_w + padL + padR + 8)
new_h = max(self._min_height, doc_h + top  + Theme.aboutHighlightTrim + 6)
```

The node stretches horizontally as the user types rather than wrapping down — the design intent is that an AboutNode label is a *line*, not a paragraph. If the user wants a paragraph they reach for WarmNode. A long label still wraps once the rect's width hits whatever the user dragged it to, but the natural growth direction is right, not down.

### Edit Activation

Double-click anywhere outside the visible button shelf zone enters edit mode. `_start_edit` flushes the device-coordinate cache (otherwise the old painted title bleeds through behind the editor overlay), then calls `_editor.start_edit(label, edit_rect)`. The editor handles position, show, and focus in one pass.

Commit fires on Enter or focus loss. Escape cancels. The committed text writes to both `data.label` and `data.title` — historically these were separate concerns; they're aliased now so older sessions that only carried `title` still survive, and new code can settle on `label` as the authoritative field.

### Shelf-via-Resize Gesture

AboutNode pioneered the resize-driven shelf reveal that several other nodes now share (VideoNode lifted it 2026-04-28). The button strip starts hidden; the user reveals it by dragging the bottom-right corner downward, and hides it by pulling back upward.

```python
_RESIZE_SHELF_REVEAL_THRESHOLD = 75.0
_RESIZE_SHELF_HIDE_THRESHOLD   = 30.0
```

Asymmetric on purpose: reveal demands a deliberate yank so a casual height nudge doesn't surface the buttons by accident; hide is lighter so the user can dial the final height down tight without the shelf clinging on past the last line of text.

The anchor (`_shelf_anchor_h`) is re-seeded after every toggle so a single continuous drag can flip the shelf multiple times. Implementation lives in `mousePressEvent` (anchor seed) and `mouseMoveEvent` (after `super()` so the rect reflects the resize, then the threshold check). The double-click on the top strip that used to toggle the shelf is gone — purely visual now.

A reveal also calls `_reshuffle_emoji()` to pick a new random emoji for the shuffle button — small touch of personality on each gesture.

### Depth Toggle — Two-State Background

AboutNode is the first adopter of the `bg_color` / `bg_color_front` convention. Each participating node type exposes paired colours in its `[node.<type>]` TOML section: a back colour for the normal Z-tier and a slightly HSL-lifted front colour for the pinned-forward state. The convention is documented in the Settlers Category Design Brief; the wiring lives in `_bg_color()` and `_apply_depth()`:

- `_bg_color()` returns the front or back colour based on `data.depth_front`, with a custom `node_tint` (user-chosen per-instance colour) overriding both when present and not in `_LEGACY_TINTS` (the two pre-tint hardcoded values that mean "use Theme default")
- `_apply_depth()` stops the ambient `bg_anim` before calling `setBrush`, otherwise `_on_bg_changed` fires after the depth toggle and overwrites the brush with the outgoing target

The animation-stop-before-setBrush order is load-bearing — the same order GitNode adopts when it joins the convention later.

### Class-Shared Font Cache

A populated session can carry hundreds of AboutNodes (drift warnings, captions, category memos all add up). Constructing a fresh `QFont` + `QFontMetrics` per instance was registering as a visible hitch on session load:

```python
_SHARED_FONTS: dict = {}
```

Keyed on the full font-identity tuple `(family, size, style)`, populated lazily on first paint, reused for every subsequent AboutNode. Memory cost negligible (a few KB per cache entry, the dict will never hold more than a handful of entries even across theme reloads); paint-time cost reduced from O(n) constructions to O(distinct-fonts).

`paint_content` falls into one of two paths:

- **Fast path** — single-line label that fits both axes. Skips `boundingRect` and line-splitting entirely. Covers the typical sticky-note case.
- **Slow path** — multi-line or overflow. Computes the bounding rect, splits lines, truncates with an ellipsis if the label exceeds the available height. Cached per `(label, width, height)` so repeat repaints on a static rect skip the bounding-rect call.

### One of Three Notification Channels

The app whispers at the user through three deliberately-distinct surfaces:

| Channel | Voice | Used for |
|---|---|---|
| **AboutNode** | sticky-note tone, persistent, spatial | drift warnings, captions, group labels — things that should hang around next to a specific node or region |
| **ClaudeResponseNode** | conversational, Claude's voice | reasoning chain output, anything with a reasoning-of-origin |
| **InfoBar** | systemic, transient | "I handled this, here's what happened" — paste-split reports, save confirmations, ephemeral status |

These are not unified on purpose. Each channel carries a different kind of information and the user reads them with different attention; flattening them would muddy the signal. AboutNode's defining property in this triad is *spatial persistence* — the message stays attached to the place on the canvas that produced it.

## Data Class

`AboutNodeData` extends `NodeData` with the standard set:

- `label: str` — the visible text (canonical field)
- `title: str` — alias of `label` for back-compat with older sessions
- `node_tint: str` — optional per-instance colour override (hex string)
- `depth_front: bool` — depth-toggle state (renders with `bg_color_front` when true)
- standard geometry — `x`, `y`, `width`, `height`, `uuid`, `node_type="about"`, etc.

## Lifecycle

### Removal

`_demolition_pre()`:

1. Disconnects the editor's `contentsChanged → _auto_expand` signal (otherwise a late edit event hits a dead slot)
2. Calls `self._editor.teardown()` which handles the editor's own proxy widget cleanup internally (PrettyEdit's recipe)
3. Nulls `self._editor`
4. Defers to BaseNode's standard sequence

If the editor was never built (the common idle case), all three steps short-circuit on the `if self._editor:` guard and the AboutNode tears down with the bare BaseNode contract.

## Technical Notes

- `_HIDDEN_TOP_OFFSET = 2.0` is tighter than the BaseNode default of 8.0. AboutNodes are sticky-note labels — the top strip is purely visual now that button reveal moved to the resize gesture, so the chrome can be flatter than on BaseNode subclasses that need a wider hit zone for a top-strip gesture.
- `_show_emoji_btn = False` — AboutNode hides the emoji button on the button strip. The shuffle button is a different control with its own emoji slot, picked randomly on every shelf reveal.
- Custom tints take precedence over the depth-toggle convention; `depth_front` only swings the brush on un-tinted nodes. When the third node joins the depth-toggle convention, the tint-vs-depth interaction is the open design question — see the brief's *Not yet resolved in the convention* note for the placeholder rationale.
- The editor's `commit_on_focus_loss=True` means clicking off the node commits the edit. `enter_commits=True` means Enter does too. Escape cancels via `keyPressEvent`. There's no explicit save button — the gesture is the commit.
- The class-shared font cache is safe to share without locking because `paint_content` only runs on the main thread. If a future render pass moves to a worker thread, the dict needs a `QMutex`; until then, lock-free.
