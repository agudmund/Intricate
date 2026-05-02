# The Performance Node

The realtime instrumentation panel — a chromeless HUD that times every paint lap the Qt event loop takes and renders the running stats as a compact grid you can park anywhere on the canvas. FPS, last/avg/min/max frame times, total paint count, current zoom, all updated at 100 ms cadence so the readings move at human-readable speed without flickering.

PerfNode is the fourth descendant of `ChromelessRoot`, after StickerNode (the alpha-PNG sticker), JoyStatsNode (the joy tamagotchi readout), and ValueNode (the image-sequence dial). It carries the same pin contract every chromeless node has — right-click → Pin to Viewport and the panel anchors to a fixed screen position regardless of canvas zoom or pan, so the live performance readings stay readable at every altitude including the aerial range. Migrated from `BaseNode` to `ChromelessRoot` on 2026-05-02; the visual identity (dark teal body, cream border, Lombardi Lake header) is preserved verbatim — only the category changes.

## Core Files

| File | Purpose |
|---|---|
| `nodes/PerfNode.py` | The node — paint pipeline, poll timer, event filter lifecycle, reset action |
| `data/PerfNodeData.py` | Pure Python dataclass — extends `ChromelessRootData`, adds Performance-specific defaults |
| `utils/paint.py` | Shared data-grid kit helpers (`make_kit`, `draw_header`, `draw_rows`, `draw_footer`) — used by HealthNode, GitNode, and PerfNode for a consistent stats-grid aesthetic |

## How It Works

### Two Ways to Create

1. **Sidebar button** — click the perf icon in the left sidebar; the node spawns at the canvas centre, installs its event filter on the view's viewport, and starts polling immediately. Singleton constraint: only one PerfNode per scene; clicking again returns the existing one.
2. **Session restore** — `from_dict` rebuilds the data including any persisted pin state, `__init__` reattaches the poll timer, `itemChange(ItemSceneHasChanged)` installs the event filter as the node enters the scene.

### The Measurement Engine — `_PaintTimer`

The actual measurement is done by a `_PaintTimer` QObject that lives separately from the node itself. It's installed as an event filter on the graphics view's viewport (`view.viewport().installEventFilter(self)`) and intercepts every `QEvent.Paint` that flows through. On each paint event, it records `time.perf_counter()` and computes the delta against the previous timestamp — that delta is one inter-frame interval in ms. The filter never consumes events (`return False`); it's fully transparent to the actual paint pipeline.

A 120-sample rolling deque holds the most recent inter-frame intervals. From that deque the filter derives FPS (1000 / mean), min/max, and the most recent frame's interval. Stalls greater than 2 seconds are excluded from the rolling window — those are external freezes (alt-tab, system pause), not frame pacing, and including them would drag the running average toward meaningless numbers. The total paint count is a separate monotonic counter that does include the stalled frames.

The filter is installed when the node enters a scene (`itemChange(ItemSceneHasChanged)`) and uninstalled in three places: scene-leave (`itemChange(ItemSceneChange, None)`), pre-shake quieting (`_quiet_for_shake`), and the demolition crew's pre-teardown (`_demolition_pre`). All three eventually flow through the same `_uninstall_filter` method, which is idempotent.

### The Read Path — Poll-Driven Repaint

The node holds no per-frame state of its own. A 100 ms poll timer fires `_refresh`, which calls `self.update()`, which schedules a repaint, which calls `paint`, which reads the live stats from `self._timer_obj` (the `_PaintTimer` instance) and draws the grid. The 100 ms interval is plenty for human-readable numbers — the actual measurement happens at frame rate, the readout cadence is decoupled.

`_refresh` is guarded with the orphan-timer pattern: a `try: self.scene()` probe raises `RuntimeError` on a dead C++ wrapper, in which case the timer stops and disconnects itself before the wrapper is reaped.

### Color Cues — Health-style Thresholds

FPS and frame times carry colour stamps that read at a glance, using the same `Theme.healthColor*` palette HealthNode uses:

| Reading | Threshold | Colour |
|---|---|---|
| FPS ≥ 50 | calm green | healthy frame pacing |
| FPS 25–49 | warn amber | noticeable but functional |
| FPS < 25 | alarm red | something is wrong |
| Avg ≤ 20 ms | calm | corresponds to ≥ 50 FPS |
| Avg 21–40 ms | warn | corresponds to 25–47 FPS |
| Avg > 40 ms | alarm | sustained slowdown |
| Max > 40 ms | warn | a recent spike, even if avg is fine |

The Min reading is always calm (it's by definition the best frame the window has seen). FPS and Last share the same colour (Last is the inverse of instantaneous FPS), so a momentary stall paints both cells warm.

### Paint Layout

`paint()` runs the chromeless-style full pipeline (the root paints nothing — every descendant owns its visual):

1. Save painter, antialiasing on
2. Body fill in `Theme.perfNodeBg` (dark teal `#1a2020`) with cream border in `Theme.nodeBorder`, drawn as a rounded rect
3. Stats content via `_paint_stats`: header (Lombardi Lake "Performance" in Chandler42 MediumOblique +6) → 8 rows (label/value pairs) → footer ("100 ms poll · 120-frame window")
4. Restore painter

The 8 rows are FPS, Last, Avg, Min, Max, Samples, Total paints, Zoom. Empty-state ("waiting for paint events…") shows when no samples have arrived yet.

The data-grid kit helpers in `utils/paint.py` do the actual drawing — `draw_header`, `draw_rows`, `draw_footer`. These are shared with HealthNode and GitNode so the three monitor nodes have identical typography, dotted-divider style, and label-value alignment. PerfNode's contribution is the row data and the colour-cue logic.

### Pin-Aware Layout

When the node is pinned (right-click → Pin to Viewport), `ChromelessRoot` flips `ItemIgnoresTransformations` on so the panel renders at fixed screen-pixel size regardless of canvas zoom. Under that flag the rect is read in screen-pixel units rather than scene units. To keep the visible layout continuous across the pin toggle at any zoom, the kit follows the same `pin_scale` capture that JoyStatsNode uses:

```python
s   = float(getattr(self.data, 'pin_scale', 1.0)) or 1.0
kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP,
               pin_scale=s)
```

The kit's `pin_scale` keyword (added in this migration — see `utils/paint.py`) multiplies font sizes, padding, line height, and divider pen width by `s`. The rect itself was multiplied by `s` in `_activate_pin`, so the kit and the rect scale together — pinning at 0.5× zoom shrinks the rect by 50% AND renders text at 50% size, keeping proportional layout intact.

Border width and corner radius also scale by `s` so the visual weight of the chrome stays proportional through the toggle:

```python
radius   = Theme.nodeRoundRadius * s
border_w = max(1, int(round(Theme.nodeBorderWidth * s)))
```

The `max(1, …)` floor ensures the border never disappears entirely on extreme down-scaling.

### Auto-Fit Height

Unlike JoyStatsNode (which carries a hardcoded 240×280 default), PerfNode's default height is computed from the actual layout at construction time. `_compute_auto_height` calls `make_kit` at `pin_scale=1.0` and sums the per-section advancement:

```
top pad + header (line_h + 22)
        + 6 breathing
        + 8 × (line_h + 3) rows
        + footer (line_h + 8)
        + bottom pad
```

With the default `line_h=18` and `pad=12`, the auto-fit lands at 264 px — enough to fit all 8 rows plus header and footer with no excess whitespace. Width stays at `Theme.perfNodeWidth` (260 px) so the user can still tune it via `settings.toml`.

The auto-fit only applies on fresh construction (`data is None`). Sessions that restore the node carry the persisted height — including any user resize via the corner grip — so the auto-fit never overrides a user choice.

### Reset Action — Context Menu

Chromeless nodes don't have a button strip, so PerfNode's "Reset Stats" action lives in the right-click context menu, appended below the built-in Pin toggle via the `_extra_context_menu_items` hook:

```python
def _extra_context_menu_items(self, ctx) -> None:
    reset_action = ctx.addAction("Reset Stats")
    reset_action.triggered.connect(self._reset_stats)
```

`_reset_stats` calls `self._timer_obj.reset()` which clears the rolling deque and the total paint counter, then `self.update()` to repaint with the empty-state placeholder until the next paint event arrives. The reset takes effect immediately and the next 120 frames refill the rolling window.

### Pre-Shake Quieting

`_quiet_for_shake()` overrides the chromeless default to stop the poll timer AND uninstall the event filter synchronously before the deferred-removeItem window opens. The filter is the critical piece: a paint event landing on a torn-down `_PaintTimer` whose Python wrapper is still alive but whose C++ side has been freed would dereference into freed memory — the same race window class that took StickerNode out as 0xc0000409 fastfail on 2026-04-18.

Calls `super()._quiet_for_shake()` first to keep the root's pin-tracking disconnect, then stops the poll timer, then uninstalls the filter. The demolition crew runs the timer teardown again afterwards via `_demolition_timers`, which is idempotent.

## Data Class

`PerfNodeData` extends `ChromelessRootData` (which extends `NodeData`). The pin fields are inherited and serialise through `super().to_dict()` chaining — no per-class bookkeeping needed.

PerfNode-specific defaults:

- `node_type: str = "perf"`
- `title: str = "Performance"`
- `width: float = Theme.perfNodeWidth` — settings.toml customisable, default 260 px
- `height: float = 240.0` — placeholder; PerfNode.__init__ overrides with `_compute_auto_height()` on fresh construction

Inherited from `ChromelessRootData`:

- `pinned: bool` — current pin state
- `pin_vp_x: float`, `pin_vp_y: float` — viewport coordinates for the pin anchor
- `pin_scale: float` — canvas zoom captured at pin time, used by paint to scale fonts and chrome

Performance readings themselves never persist — the rolling window resets to empty on every restore. Only the geometry, identity, and pin state survive.

## Lifecycle

### Creation

`Scene.add_perf_node(pos)` → singleton check (returns existing if any) → `PerfNode()` → fresh `PerfNodeData` with auto-fit height → `ChromelessRoot.__init__` sets pos/z/flags/pin state → `setBrush(perfNodeBg)` → poll timer started. Filter install fires lazily on `itemChange(ItemSceneHasChanged)` after `addItem`.

### Session Restore

`PerfNodeData.from_dict(d)` → `PerfNode(data)` → same `__init__` flow as fresh, but the `is_fresh` branch is skipped so `data.height` carries the persisted size. Pin state is restored via `ChromelessRoot.__init__` deferring `_activate_pin(from_saved_vp=True)` to the next event-loop tick so the saved viewport coords land in the correct view transform.

### Removal

Two paths converge on the same demolition crew:

1. **Shake-delete** — shake the node hard → `_on_shake_triggered` (inherited from `ChromelessRoot`) → `_quiet_for_shake` (stops poll timer + uninstalls filter + disconnects pin tracking) → particle burst → `arm_cooldown` → `removeItem` deferred one tick → scene-leave → `itemChange(ItemSceneChange, None)` → `demolish(self)` from the shared crew
2. **Direct scene-leave** — session switch or vaporize → `itemChange(ItemSceneChange, None)` runs first (my override stops timer + uninstalls filter), then super's demolish hook fires

`_demolition_pre` calls super's pin-tracking disconnect, then uninstalls the filter again (idempotent). `_demolition_timers = [('_poll_timer', '_refresh')]` declares the timer for the crew's standard teardown sequence.

## Technical Notes

- The `_PaintTimer` filter measures whatever paints flow through the view's viewport — node paints, connection wire paints, particle effects, the View's own `drawBackground` and `drawForeground`. It's a pure pipeline-throughput meter; it doesn't distinguish between cheap and expensive paints, just counts the wall-clock interval between consecutive paint events on the viewport widget. That's the metric that matches "perceived smoothness" for the user.
- The 2-second stall threshold (`if dt_ms < 2000.0`) is deliberately permissive. Anything under 2 s is paint-pipeline behaviour; anything over is the OS suspending the app. Without the threshold a single alt-tab would push the rolling average toward thousands of ms and take 120 subsequent frames to recover.
- The poll timer is an orphan (`PerfNode` is `QGraphicsRectItem`-based, not a `QObject`-derived widget), so `_refresh` carries the canonical orphan-timer guard: `try: self.scene()` raises `RuntimeError` on a dead C++ wrapper, the slot stops + disconnects the timer and bails. Same guard pattern documented for the dashboard-node family (HealthNode, GitNode, JoyStatsNode).
- The `_install_filter` call in `__init__` is a fallback for unusual restore paths where the scene is already attached before the constructor returns. The normal path is `addItem` → `itemChange(ItemSceneHasChanged)` → `_install_filter`. Both paths are guarded by `if self._timer_obj is not None: return`.
- Pinned PerfNode paints at full natural pipeline regardless of canvas zoom because `ItemIgnoresTransformations` makes the painter's worldTransform identity. The aerial-zoom shortcut in `BaseNode.paint` doesn't apply (PerfNode doesn't inherit `BaseNode`), and the LOD check in `Connection.paint` doesn't apply either (PerfNode has no wires). The HUD stays fully readable at any altitude including the aerial range — which is the architectural reason for the migration.
- Border width scales by `pin_scale` so a node pinned at 0.5× zoom doesn't show a hairline border at twice the relative size of a node pinned at 1.0×. The `max(1, …)` floor guarantees the border survives extreme down-scaling.

## Relationship to Other Systems

- **`utils/paint.py`** — the data-grid kit shared with HealthNode and GitNode. PerfNode added the `pin_scale` keyword to `make_kit` during this migration; the parameter defaults to 1.0 so HealthNode and GitNode continue to behave identically. When those nodes eventually migrate to chromeless, they will pass `data.pin_scale` the same way PerfNode does and benefit from the same kit-follows-IIT contract.
- **`ChromelessRoot`** — provides pin, shake-delete, drag-commit dead zone, demolition hookup, and the resize grip via `_UNPINNED_RESIZE_ENABLED = True`. See `Documents/Design/Chromeless Nodes.md` for the framework-level docs.
- **`Theme`** — `Theme.perfNodeBg` (`#1a2020`) is the dark teal body fill, kept distinct from the standard `Theme.nodeBg` so the perf monitor reads as instrumentation rather than content. `Theme.perfNodeWidth = 260.0` is the default width; height is computed dynamically. `Theme.healthColor*` keys drive the colour-cued threshold rendering.
- **`Documents/Design/Zoom Level.md`** — pinned PerfNode is the canonical example of "HUD that stays readable at every altitude including aerial." The architectural reason it works is the IIT-on identity worldTransform, which is the same mechanism every chromeless pinned node uses.
