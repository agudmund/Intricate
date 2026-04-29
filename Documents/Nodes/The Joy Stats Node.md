# The Joy Stats Node

The realtime readout for the joy mechanic — a chromeless dashboard that paints a compact stats grid every second so you can watch the tamagotchi breathe while you tune it. Bar percentage, current state, grace countdown, happy accumulator, bucket count, depletion rate, feed window, hunger flag — all in one small panel that lives wherever you park it on the canvas.

JoyStatsNode is the second descendant of `ChromelessRoot` (StickerNode was the first). No chrome, no title bar, no buttons, no ports — just a rounded background and a two-column block of live numbers. It paints itself, polls itself, never participates in the wire graph. The whole point is to be a quiet instrument you glance at, not a node you reason about structurally.

## Core Files

| File | Purpose |
|---|---|
| `nodes/JoyStatsNode.py` | The node — paint, poll timer, demolition manifest |
| `data/JoyStatsNodeData.py` | Pure Python dataclass — extends `ChromelessRootData` (pin state, geometry) |

## How It Works

### Two Ways to Create

1. **Sidebar button** — click the joy stats icon in the left sidebar; the node spawns at the canvas centre and starts polling immediately
2. **Session restore** — `from_dict` rebuilds the data, `__init__` starts a fresh 1-second poll timer, the next paint fills in current values from the running app

### The Read Path — One Reach Per Second

The node holds no state of its own beyond pin and geometry. Every second the poll timer fires `_refresh`, which forces a repaint, which calls `paint_content`, which reaches into the IntricateApp main window via `self.scene().views()[0].window()` and pulls the live joy state directly from the running mechanic:

```
joy_bar.value()          → bar percentage
_joy_sleeping            → sleep mode flag
_joy_in_grace            → grace flag
_joy_grace_remaining     → grace countdown (sec)
_joy_happy_secs          → happy accumulator (sec)
_joy_bucket_count        → buckets earned
_JOY_BUCKET_SECS         → seconds-per-bucket target
_joy_hungry              → hunger flag
_feed_timestamps         → recent feed log
_FEED_MAX, _FEED_WINDOW  → feed-rate limit + window
_joy_timer.interval()    → current depletion tick (ms)
_JOY_GRACE_SECS          → grace-window total
```

No signals, no callbacks, no shared state — the node polls. Game-balance instrument first; it samples the mechanic at a clean cadence rather than reacting to internal events that could mislead a tuning session by under- or over-firing the readout.

### State Label

A four-state label tells you which regime the bar is in, with a colour cue:

| State | When | Colour |
|---|---|---|
| `Sleeping` | sleep mode is on | dusk blue `#6688aa` |
| `In Grace` | bar is at 100% and the grace window is running | warm green `#7ab88a` |
| `Hungry!` | bar dropped below the hungry threshold without a feed | rose `#d87a7a` |
| `Awake` | the resting state — bar draining, grace expired, not yet hungry | wheat `#b8b872` |

The `Hungry` line at the bottom of the grid mirrors the same colour when the flag is true, so a glance can spot urgency without reading numbers.

### Feed Window

`Feeds: N/M (reset Ks)` reports how many feeds are still counted in the rolling rate-limit window plus when the next slot opens. Built from `_feed_timestamps` and the `_FEED_MAX` / `_FEED_WINDOW` pair. When the window has burned all its feed slots, the `(reset Ks)` suffix shows seconds until the oldest one ages out and the user can feed again.

### Paint Layout

Single rounded rect filled with `Theme.aboutBgColor` (alpha-blended via `Theme.aboutTransparency` so the canvas blur breathes through), then text painted on top in two passes:

1. **Title** — "Joy Stats" at the top-left in Chandler42 MediumOblique +6, in the Lombardi Lake teal `#72b8b8`
2. **Body** — the stats grid in Lato −1 at 0.85 opacity, three logical groups separated by short gaps: bar+state, grace+happy+buckets, depletion+feeds+hunger

The vertical layout constants (`_TITLE_TOP_PAD`, `_BODY_TOP_PAD`, `_LINE_HEIGHT`) are class attributes so future tuning doesn't require recompiling — but unlike the joy mechanic itself, these are presentation knobs, not game-balance knobs, and live in code rather than `settings.toml`.

### Pin-Aware Layout

When the node is pinned (right-click → Pin to Viewport), `ChromelessRoot` flips `ItemIgnoresTransformations` on so the node renders at fixed screen-space size regardless of canvas zoom. Under that flag the rect's units shift from scene-space to screen-pixel-space. To keep the visible layout continuous across the pin toggle, every layout constant is multiplied by `data.pin_scale` (the zoom level captured at pin time, 1.0 when unpinned):

```python
s         = float(getattr(self.data, 'pin_scale', 1.0)) or 1.0
pad       = self._CONTENT_PAD   * s
title_top = self._TITLE_TOP_PAD * s
title_h   = self._TITLE_HEIGHT  * s
body_top  = self._BODY_TOP_PAD  * s
line_h    = self._LINE_HEIGHT   * s
```

Same trick for the font sizes — `(Theme.aboutFontSize + bump) * s`. The visible result: pinning at 0.6× zoom doesn't suddenly shrink the readout's text by 40%; the rect was multiplied by 0.6 in `_activate_pin`, the constants are multiplied here, the visible size stays continuous. See `ChromelessRootData.pin_scale` for the full rationale.

## Pre-Shake Quieting

`_quiet_for_shake()` overrides the chromeless default to stop the poll timer synchronously before the deferred-removeItem window opens. Without this, a 1-second tick landing between the shake firing and the actual scene-leave can dispatch `_refresh` onto a node that's about to vanish — the same race window that took StickerNode out as 0xc0000409 fastfail on 2026-04-18.

The compliance lift on 2026-04-29 (see `Documents/Compliance/Node Cleanup Compliance.md`) added the synchronous-quiet hook at the root level and JoyStatsNode overrides to add timer-stop on top. Demolition crew still tears the timer down via `_demolition_timers = [('_poll_timer', '_refresh')]` after scene-leave; this method just closes the interim window.

## Data Class

`JoyStatsNodeData` extends `ChromelessRootData` with no node-specific fields beyond what every chromeless node already carries:

- `pinned: bool` — viewport-pin state
- `pin_vp_x, pin_vp_y: float` — pinned viewport coordinates (screen pixels)
- `pin_scale: float` — zoom captured at pin time (layout-scale multiplier)
- standard geometry — `x`, `y`, `width`, `height`, `z_value`, `uuid`, `node_type="joy_stats"`

Default size: 240 × 280. The node is sized to fit the stats grid at 1.0× zoom; resize via the bottom-right corner grip while unpinned to set the frozen size before pin.

## Lifecycle

### Creation

`Scene.add_joy_stats_node(pos)` → `JoyStatsNode(JoyStatsNodeData())`. The node's `__init__` starts the 1-second poll timer immediately; `_refresh` self-guards on `self.scene() is None` so the first tick before scene attachment is a no-op.

### Session Restore

`JoyStatsNodeData.from_dict(d)` → `JoyStatsNode(data)`. Same poll-timer init as a fresh spawn. Pin state is restored via `ChromelessRoot.__init__` deferring `_activate_pin(from_saved_vp=True)` to the next event-loop tick so the saved viewport coords land in the correct view transform.

### Removal

Two paths converge on the same demolition crew (see `Documents/Compliance/Node Cleanup Compliance.md` for the full sequence):

1. **Shake-delete:** `_on_shake_triggered` fires → `_quiet_for_shake` (stops poll timer + disconnects pin tracking) → particle burst → `arm_cooldown` → `removeItem` deferred one tick → scene-leave → `itemChange` → `demolish(self)`
2. **Direct scene-leave:** session switch or vaporize → `removeItem` runs synchronously → `itemChange` → `demolish(self)`

`demolish` reads `_demolition_timers` and stops + disconnects the poll timer. `_demolition_pre` (logged frame-by-frame for the cross-node-destruction forensic trail) calls `super()._demolition_pre()` which severs viewport tracking. No proxies, no media players, no background threads — minimal teardown.

## Game-Balance Workflow

JoyStatsNode is the realtime feedback half of the GDC-style tuning loop established 2026-04-29. The four configuration dials in `[intricate.joy]` (awake drain, sleep drain, grace seconds, bucket minutes) and the two state-override sliders (bucket count, bar value) live in The Settlers; this node is where you watch the consequences:

```
Settlers slider → settings.toml writes
                → settings watcher fires
                → IntricateApp._apply_joy_settings re-applies
                → next JoyStatsNode poll picks up new state
                → readout shifts
```

For the override sliders the path is one hop shorter — Settlers writes the sidecar file directly, the running app's `JoyBucketsWatcher` / `JoyStateWatcher` picks it up, JoyStatsNode's next poll reflects it.

End-to-end latency from slider drag to visible change in JoyStatsNode is bounded by the 1-second poll, not the watcher hops.

## Technical Notes

- The poll timer is an orphan (no QObject parent — JoyStatsNode is `QGraphicsRectItem`-based), so `_refresh` carries the canonical orphan-timer guard: `try: self.scene()` raises `RuntimeError` on a dead C++ wrapper, the slot stops + disconnects the timer and bails. Same guard pattern documented for the dashboard-node family (HealthNode, GitNode, et al.).
- `aboutFontSize` is read from Theme rather than hardcoded so the readout follows the same theme-reload rhythm as About-family nodes — change the About font size in The Settlers and JoyStatsNode shifts with it.
- The state-colour palette is hardcoded rather than themed. Each colour is meaningful (sleep = cool, grace = vital, hungry = warning, awake = neutral) and the chosen tones lean warmer than the canvas backdrop so the readout pops without screaming. Promote to Theme keys if a future palette pass calls for it.
- `_get_window()` walks `scene → views()[0] → window()` to reach `IntricateApp`. Returns `None` if any link is missing, in which case `paint_content` paints a small `"no window"` placeholder and exits — the node stays alive and resumes painting normally on the next tick once the scene graph is whole again.
