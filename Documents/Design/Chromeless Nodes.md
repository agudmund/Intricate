# Chromeless Nodes

A second category of canvas citizen, parallel to the BaseNode-derived structural nodes. Where BaseNode nodes are the data graph — title, ports, button strip, body content, hover pulse, wires — chromeless nodes are HUDs and ornaments: pinnable to the viewport, free of structural apparatus, owning their own visual entirely. The family exists because the canvas has two distinct kinds of inhabitants, and forcing one root to serve both produces a permanent inheritance tax in either direction. This document covers the framework — `ChromelessRoot`, `ChromelessRootData`, the contracts every descendant must honour. Per-node specifics (StickerNode, JoyStatsNode, ValueNode, future PerfNode) live in their own docs in `Documents/Nodes/`.

## Two Roots, Two Mental Models

Intricate has two parallel root classes, both inheriting `QGraphicsRectItem` directly. They are siblings, not parent and child:

| Root | What it is | Examples |
|---|---|---|
| `BaseNode` | Structural data nodes — interlinked pieces of thinking, with title, ports, button strip, body, hover pulse | WarmNode, AboutNode, MarkdownNode, ImageNode, GitNode |
| `ChromelessRoot` | HUDs and ornaments — pinnable to the viewport, no structural apparatus, self-painting | StickerNode, JoyStatsNode, ValueNode |

The split is a category distinction, not a styling difference. A chromeless node is not "a BaseNode without chrome" — it's a different kind of canvas citizen entirely, with its own contract for how it appears, how it interacts, how it persists, and how it leaves the scene. Forcing chromeless nodes to inherit from BaseNode (the historical state) created a permanent silencing tax: every BaseNode feature added meant another override in the chromeless subclasses to suppress it. The 2026-04-18 detachment refactor extracted the chromeless contract into its own root and made the two families coequal.

The visual style of any individual node is up to that node — chromeless nodes can carry borders, backgrounds, transparent fills, anything that fits their role. PerfNode, when it migrates, will keep its current border and body weight even though StickerNode and ValueNode are alpha-transparent and JoyStatsNode is a flat rounded panel. The root is about category, not look.

## Core Files

| File | Purpose |
|---|---|
| `nodes/ChromelessRoot.py` | Base class — pin contract, shake-detect, context menu, demolition hookup, drag-commit gate |
| `data/ChromelessRootData.py` | Pure Python dataclass — extends `NodeData` with the four pin fields and serialises them via `super().to_dict()` chaining |
| `nodes/_demolition.py` | Shared demolition crew — same one BaseNode uses; tolerates missing connections / behaviour / buttons / ports |
| `nodes/_shake_detect.py` | Shake gesture detection — composition rather than inheritance, both root families share it |
| `nodes/_dialog_helper.py` | Extra-window choreography — `_DialogChoreographyMixin` handles the WHEN of dialog spawning (curtain dance + HWND settle); ChromelessRoot inherits it as a second base, same mixin also serves `BaseNode` and `IntricateApp` via the `_get_main_window` extension point. The HOW (Qt-managed `QDialog` base with screen centring + topmost-band defence) lives in Pretty Widgets as `pretty_widgets.PrettyDialog` |

## The Pin Contract

Pinning is the headline feature. A pinned chromeless node anchors to a point in the **viewport** rather than the scene, so it stays at a fixed screen position regardless of how the user pans or zooms the canvas. It is what makes HUD nodes possible — a stats readout you can park in a corner of the viewport and read from any zoom altitude.

### The four pin fields

`ChromelessRootData` carries four fields:

| Field | Type | Purpose |
|---|---|---|
| `pinned` | `bool` | Whether the node is currently in screen-space mode |
| `pin_vp_x`, `pin_vp_y` | `float` | Viewport coordinates (view-local pixels) the node snaps back to on every pan/zoom |
| `pin_scale` | `float` | Zoom captured at pin time, used as a layout-scale multiplier in paint |

`pin_scale` is the subtle one. Under `ItemIgnoresTransformations` (set on while pinned), the painter renders text and rect at full point size regardless of canvas zoom — but the rect's units shift from scene-space to screen-pixel-space at the toggle. Without compensation, pinning at zoom != 1× would visibly snap the node's text size by the zoom factor. `_activate_pin` captures the current zoom into `pin_scale`, multiplies the rect by it (so the visible size stays continuous), and `paint_content` multiplies layout constants and font sizes by it on every paint. Unpin restores `pin_scale = 1.0` and divides the rect back. The pair makes pin/unpin a visually silent operation at any zoom level.

### Activation and deactivation paths

`_activate_pin(from_saved_vp: bool = False)` has two callers:

1. **User-initiated** (`from_saved_vp=False`) — right-click → Pin to Viewport. Captures the current scene-space rect through the current zoom into `pin_scale`, multiplies the rect to land at the equivalent screen-pixel size, computes `pin_vp` from `view.mapFromScene(self.pos())`, then flips on `ItemIgnoresTransformations` and connects viewport tracking.
2. **Session restore** (`from_saved_vp=True`) — `__init__` defers a `singleShot(0, self._activate_pin(from_saved_vp=True))` if `data.pinned` was True at save time. The saved `pin_vp` and `pin_scale` are *honoured*, not recomputed. (The 2026-04-22 bug had restore always overwriting `pin_vp` from the current view transform, which fired before camera restore and produced garbage coordinates — fixed by the two-path split.)

`_deactivate_pin` is the inverse: divide the rect back by the captured zoom, reset `pin_scale = 1.0`, flip `ItemIgnoresTransformations` off, disconnect viewport tracking, restore `ItemIsMovable`.

### Viewport tracking

While pinned, the node listens for `view.viewTransformed` (Intricate-specific signal emitted on every transform mutation), plus `horizontalScrollBar().valueChanged` and `verticalScrollBar().valueChanged` as secondary channels for the rare scrollbar-only case. On every emission, `_on_viewport_changed` calls `view.mapToScene(pin_vp_x, pin_vp_y)` and `setPos`es to the resolved scene position. The result: as the user pans or zooms the canvas, the node visibly stays put.

`viewTransformed` is the primary channel because Qt does not provide a native transform-change signal — it's emitted from `IntricateView.scale()` and `IntricateView.translate()` overrides (the "passive single source of truth" pattern, see `Documents/Design/Zoom Level.md`).

### The IIT trick

`ItemIgnoresTransformations` is a Qt flag that strips the view transform from an item's rendering. While pinned, every pinnable chromeless node has it on — which is what makes them readable at any zoom altitude including the aerial range (see `Documents/Design/Zoom Level.md`). Notably, the painter's `worldTransform()` for an IIT-on item is identity, so `levelOfDetailFromTransform` reads as 1.0 and the aerial-zoom shortcut in BaseNode never applies. Pinned chromeless nodes paint at full natural pipeline regardless of canvas zoom, by design.

## Shake-Delete

Every chromeless node participates in the shake-to-delete gesture by default. The detection lives in `nodes/_shake_detect.py` and is held by composition — `ChromelessRoot.__init__` constructs a `ShakeDetector` and wires its `on_shake` callback to `self._on_shake_triggered`. Shaking enough to trip the detector fires the default removal: synchronous quieting, particle burst, cooldown arm, deferred `removeItem`.

### `_quiet_for_shake` — the synchronous race-closing hook

The deferred removeItem (`QTimer.singleShot(0, removeItem)`) opens a one-tick window between shake-fire and the actual scene-leave. Anything that ticks in that window — viewport-tracking signals, poll timers, slider scrubs — can land on a node about to vanish and collide with its destructor (the `0xc0000409` fastfail class, originally caught on StickerNode 2026-04-18).

`_quiet_for_shake()` runs *before* the deferred-remove is scheduled and synchronously severs anything that could fire mid-window. The root's default body disconnects viewport tracking; subclasses with additional moving parts (poll timers, slider proxies, media players) override and call `super()`:

```python
def _quiet_for_shake(self):
    super()._quiet_for_shake()
    self._poll_timer.stop()
    # ... type-specific synchronous quieting
```

This is parallel to `_demolition_pre` (which fires *after* scene-leave) — both are needed because the demolition crew tears everything down properly but only after the deferred-remove tick. `_quiet_for_shake` closes the interim window; `_demolition_pre` does the proper teardown.

### Subclass override of `_on_shake_triggered`

Subclasses can override the full shake response to customise behaviour — StickerNode, for example, picks between `sprinkle` and `orbital_burst` particle effects based on the alpha coverage of the sticker. The override should still call `_quiet_for_shake`, `arm_cooldown` (to prevent rapid shakes cascading across neighbouring nodes), and schedule the `removeItem` via singleShot so the burst gets a frame to render.

## Right-Click Context Menu

Chromeless nodes have no button strip — interaction surfaces collapse onto the right-click context menu. The root's `_show_context_menu` builds a `PrettyMenu`, adds a built-in checkable "Pin to Viewport" toggle wired to `_toggle_pin`, then calls the subclass hook:

```python
def _extra_context_menu_items(self, ctx) -> None:
    """Override hook — subclasses extend the right-click menu."""
    pass
```

The hook runs after the pin toggle so subclass entries appear below it. Typical use:

```python
def _extra_context_menu_items(self, ctx):
    reset_action = ctx.addAction("Reset Stats")
    reset_action.triggered.connect(self._reset_stats)
```

Since chromeless nodes lack the button strip BaseNode provides, the context menu is the canonical home for any node-specific actions: reset, reload, refresh, browse-for-image, copy-to-clipboard. Pack interaction options into this hook rather than reaching for any other UI surface.

## File-Dialog Choreography

`ChromelessRoot` inherits `_DialogChoreographyMixin` (`nodes/_dialog_helper.py`) as a second base, so any chromeless subclass that needs a file picker, save dialog, or directory chooser gets the same Windows-foreground behaviour `BaseNode` provides. Wrap the dialog call in the context manager and use the yielded main window as the dialog parent:

```python
def _browse_for_image(self):
    with self._dialog_choreography() as mw:
        path, _ = QFileDialog.getOpenFileName(
            mw, "Choose Image", "", "Images (*.png *.jpg *.jpeg)"
        )
    if path:
        self._load_from_path(path)
```

The choreography drops the always-on-top window flag, rolls curtains up if they're down, drains the HWND-recreation aftermath, focuses the main window so the dialog parents to a real foreground HWND, then restores everything on exit. Without it, dialogs spawn parented to a not-yet-foregrounded HWND and Windows silently refuses to surface them — they appear to be missing entirely (the symptom that triggered this extraction). See the docstring in `_dialog_helper.py` for the three settle-points (post-`_drop_topmost` drain, curtain-anim wait with safety timeout, post-activate drain) that make this reliable on Windows.

StickerNode's empty-sticker double-click is the canonical chromeless usage; future raw-image-style chromeless nodes that browse for source files inherit the same flow at zero cost.

The choreography is one half of a two-piece **extra-window framework**. The other half — `pretty_widgets.PrettyDialog` — is a `QDialog` subclass that handles HOW Qt-managed popups (frameless themed dialogs like GitNode's commit prompt, the new-session masterpiece input, the rare ceremony exceptions to Intricate's mostly-popup-free Z-depth workflow) hold their ground once shown: explicit screen centring plus cross-OS topmost-band defence. Lives in Pretty Widgets so other family apps (Pebbles, Majestic) can inherit it directly without depending on Intricate. Compose the two — wrap a `PrettyDialog.exec()` in `with self._dialog_choreography() as mw:` — and the dialog gets curtain-dance + screen-centred + topmost-band defence in one. Native OS dialogs (`QFileDialog` and friends) only need the choreography; they're owned by the OS shell and defend themselves via the OS's own positioning rules.

## Generic Resize Grip

`ChromelessRoot` provides an opt-in bottom-right corner-grip resize for unpinned nodes. The subclass declares opt-in with a class attribute:

```python
class MyChromelessNode(ChromelessRoot):
    _UNPINNED_RESIZE_ENABLED = True
```

While unpinned, dragging the bottom-right `_RESIZE_GRIP_SIZE` square (default 18 px in scene units) of the rect resizes the node. The shake detector is suppressed for the duration of the resize so the gesture can't be mistaken for a shake. Subclasses can override `setRect` to re-anchor any internal layout (ports, proxy widgets) on every size change.

The resize gesture only works while unpinned — that's by design. The flow is "resize while unpinned to set the frozen screen size, then pin to lock it." Once pinned, the rect is the screen-space size and resizing while pinned would be ambiguous (does the user mean to change the screen size, or the underlying scene-space rect, or both?) — so the grip is gated off.

StickerNode opts out of the generic grip (`_UNPINNED_RESIZE_ENABLED = False`) and provides its own bespoke resize with aspect-ratio preservation and cursor-hide; everything else opts in.

## Drag-Commit Dead Zone

A Wacom-pen tap can produce a stream of synthesized `WM_MOUSEMOVE` events as Windows transitions the OS cursor from its previous location to the pen contact point. Qt sees these as legitimate motion and translates the item along the synthesized path — manifesting as "node propelled offscreen on touch" or, when the synthesized reversal pattern hits the shake threshold, "node deleted on touch." Diagnosed 2026-04-29 from forensic logs.

`ChromelessRoot` includes a drag-commit dead zone at the root level. From mousePress, until cumulative cursor travel exceeds `_DRAG_COMMIT_THRESHOLD_PX` (default 12 screen px), `mouseMoveEvent` is suppressed: super is not called (so the item doesn't translate) and the shake detector receives no samples (so phantom reversal accumulation can't fire). Real human drags blow past 12 px in a single event, so genuine motion releases the gate instantly with no perceptible delay. Stationary taps stay stationary.

The gate logs at INFO when it catches suppressed motion and at TRACE for committed drags — useful when investigating any future phantom-motion incidents.

## Demolition Crew

Chromeless nodes participate in the same demolition crew BaseNode uses — `nodes/_demolition.py` is shared. `QGraphicsRectItem` doesn't know about `_prepare_for_removal` (that's a BaseNode contract), so the chromeless root hooks in via `itemChange` and the `ItemSceneChange` event:

```python
def itemChange(self, change, value):
    if (change == QGraphicsItem.ItemSceneChange and value is None
            and not self._removal_done
            and not getattr(self, '_pinned_across_scenes', False)):
        self._removal_done = True
        from nodes._demolition import demolish
        demolish(self)
    return super().itemChange(change, value)
```

The crew tolerates missing parts. Chromeless nodes have no `connections` (well, an empty list), no `behaviour`, no `_buttons`, no `_ports` — the crew checks each part for existence and runs only the applicable steps.

### Subclass declaration of teardown work

Two class attributes let subclasses tell the crew what they own:

| Attribute | Format | Purpose |
|---|---|---|
| `_demolition_timers` | `[(field_name, slot_name), ...]` | QTimers to stop and disconnect by field name |
| `_demolition_proxies` | `['_proxy_field_name', ...]` | QGraphicsProxyWidgets to tear down (widget → setParent(None) → deleteLater) |

JoyStatsNode declares `_demolition_timers = [('_poll_timer', '_refresh')]` for its 1-second poll. ValueNode declares `_demolition_proxies = ['_slider_proxy']` for its scrubber. The crew reads these and runs the appropriate teardown.

### `_demolition_pre` — type-specific pre-teardown

For anything beyond timers and proxies (custom signal connections, event filters, media players), subclasses override `_demolition_pre` and call super:

```python
def _demolition_pre(self):
    super()._demolition_pre()      # disconnects viewport tracking
    self._uninstall_event_filter()
    self._media_player.setSource(QUrl())
```

Super does the root's pin-tracking disconnect — always call it.

`_pinned_across_scenes` is a safety override on `BaseNode` that suppresses the scene-leave demolition for app-scoped nodes that need to transfer through limbo (Companion ClaudeNode, future HUDs). Chromeless nodes can opt in too if they need cross-session persistence, but the default is off — most chromeless nodes are session-bound.

## Adding a New Chromeless Node

The full recipe to introduce a new chromeless descendant:

1. **Data class** — `data/MyNodeData.py` extending `ChromelessRootData`. Add type-specific fields (cache keys, frame paths, whatever); the four pin fields come for free. Implement `from_dict`. `to_dict` chains through `super().to_dict()` so pin fields always serialise.
2. **Node class** — `nodes/MyNode.py` extending `ChromelessRoot`. Override `paint(painter, option, widget=None)` entirely (the root paints nothing). If the layout has constants that should scale across pin, multiply them by `data.pin_scale` in `paint`.
3. **Opt into the resize grip** — `_UNPINNED_RESIZE_ENABLED = True` on the class if you want a generic corner-drag resize. Skip if the node has its own bespoke gesture.
4. **Context menu** — override `_extra_context_menu_items(ctx)` if there are node-specific actions. The pin toggle is built in.
5. **Teardown declarations** — add `_demolition_timers` and `_demolition_proxies` for any QTimers and QGraphicsProxyWidgets the node owns. Override `_quiet_for_shake` to add synchronous-stop calls if there's anything that ticks (poll timers, animations).
6. **Factory + registration** — add `Scene.add_my_node(pos)` in `graphics/Scene.py`. Add a branch in `Scene._restore_node` for `node_type == "my_node"`. Register `"my_node"` in `utils/persistence/session.py` `_KNOWN_TYPES`.
7. **Sidebar wire** — add a sidebar button and `_spawn_my_node` in `main_window.py`.
8. **Documentation** — `Documents/Nodes/The MyNode.md` covering the type-specific story (paint layout, what it reads from where, lifecycle quirks).

The root carries pin, shake, context menu, drag-gate, demolition hookup, and the corner grip if opted in. The subclass owns its full visual, its data shape, its actions, and any extra ticking parts.

## Technical Notes

- **The root paints nothing.** `ChromelessRoot.paint()` is an empty method by design. Subclasses override it entirely with no `super()` call required. This is deliberately different from BaseNode where subclasses override `paint_content` and the base draws the chrome — chromeless subclasses *are* their full visual.
- **`connections` exists but stays empty by default.** The attribute must exist because `graphics/Connection.py` and the scene's chain-select walkers duck-type on it. Subclasses with real ports (ValueNode) manage the list themselves.
- **The forensic logging in `ChromelessRoot.py` is heavy by design.** Chromeless nodes had a cross-node-destruction incident on 2026-04-22 (clicking JoyStatsNode occasionally took a neighbouring StickerNode with it, not replicable on demand). Every interesting codepath emits log lines so the next occurrence leaves a paper trail. When the bug is caught and closed, these can be demoted to DEBUG or stripped.
- **`shiboken6.isValid(self)` guards the viewport-tracking callback.** A transform tick firing into a chromeless node mid-teardown tripped 0xc0000409 on the original 2026-04-18 incident. The Python wrapper can outlive the C++ side briefly during teardown; `shiboken6.isValid` is the live check.
- **`_pin_connected` is the idempotency flag for viewport tracking.** Both `_connect_viewport_tracking` and `_disconnect_viewport_tracking` early-return if the flag is in the wrong state, so calling either twice is safe.
- **Pin restore is `singleShot(0, ...)` deferred.** `__init__` cannot pin synchronously because `self.scene()` is None until after `addItem` runs. The defer waits one tick for the scene/view to be wired, then activates the pin with `from_saved_vp=True` so the saved coordinates are honoured.

## Relationship to Other Systems

- **BaseNode** — sibling root, same Qt parent (`QGraphicsRectItem`). Both families coexist on the same canvas, both serialise through the same session JSON (each item's `node_type` keys into the right `_restore_node` branch), both ride the same demolition crew. The two roots don't talk to each other directly; they talk to the same scene.
- **Zoom Level** (`Documents/Design/Zoom Level.md`) — pinned chromeless nodes paint at full natural pipeline at any canvas zoom because IIT-on items have identity worldTransform, which makes the aerial-mode threshold check read as LOD 1.0. This is the architectural reason HUD nodes work at every altitude.
- **Theme** — chromeless nodes read theme constants the same way BaseNode-derived nodes do (`Theme.aboutBgColor`, `Theme.aboutFontSize`, `Theme.textPrimary`). The metaclass fallback (returning a sentinel for missing keys) applies identically.
- **Session persistence** — chromeless nodes serialise through the same `to_dict` / `from_dict` flow. `ChromelessRootData.to_dict` chains super and adds the pin fields; subclass `to_dict` chains super and adds its type-specific fields. Round-trip works through any number of inheritance levels because every layer chains through super().
- **Particles** — `_on_shake_triggered` calls `graphics.Particles.sprinkle(scene, center, count=8000)` for the default shake-burst. Subclasses can pick a different particle effect (StickerNode's `orbital_burst`) — same particle system, different shape.
