# Zoom Level

The canvas's altitude system. Intricate's view zoom does double duty — it's the user's navigation control *and* the signal that switches the canvas between two operating modes: a street-level interactive surface where every node is fully painted, fully hoverable, fully alive, and a navigation-altitude map where the canvas reads as a constellation of node positions for the next swoosh-down. This document covers every input channel that drives the zoom factor, the slider's non-linear curve, and every system on the canvas that adapts its behaviour based on what zoom level is currently active.

## The Single Source of Truth

`IntricateView.current_zoom` is the canonical scalar. Every input channel routes through `_apply_zoom(factor, anchor)`, which clamps to `[ZOOM_MIN, ZOOM_MAX] = [0.03, 5.0]` and emits `viewTransformed` so any pinned overlay (StickerNode in pinned mode, future screen-space HUDs) can re-anchor without polling. There is one zoom value, one method that mutates it, one signal that announces the change.

```
ZOOM_MIN  = 0.03   (33× zoomed out)
ZOOM_MAX  = 5.0    (5× zoomed in)
```

The 0.03 floor was extended from the original 0.10 on 2026-04-18 to accommodate large auto-split chains — once a 5 MB paste becomes a 100+ node chain, the old floor stopped being enough to see the whole shape at once. The 0.03 value also aligns exactly with slider integer 3 so the slider's bottom rung is reachable in one drag.

## The Four Input Channels

| Channel | Trigger | Factor | Anchor |
|---|---|---|---|
| **Mouse wheel** | Wheel up / down | `1.25` zoom in, `0.8` zoom out | Cursor position |
| **Alt + Right-drag** | Hold Alt + right mouse, drag vertically | `1.005 ^ -dy` per pixel | Cursor position at drag start |
| **Zoom slider** | Drag the vertical slider in the sidebar | Targets absolute zoom via Hermite curve | Viewport centre |
| **Programmatic** | Sidebar buttons, "fit to chain", session restore | Caller-specified factor | Caller-specified anchor |

All four ultimately call `_apply_zoom(factor, anchor)`, so cursor-anchored zoom is consistent across wheel and Alt-drag, and slider-driven absolute zoom anchors to the viewport centre so the canvas doesn't drift sideways during a vertical slider pull.

The wheel's `1.25` factor produces a pleasant five-clicks-to-double rhythm. Alt-drag's `1.005 ^ -dy` is gentle Photoshop-style continuous zoom — a 100 px vertical drag shifts zoom by ~1.65×. Both anchor at the cursor so whatever the user is pointing at stays under the cursor as the canvas scales.

## The Slider Curve

The zoom slider has range `[0, 1000]` and maps to `[ZOOM_MIN, ZOOM_MAX]` via a piecewise cubic Hermite that's intentionally non-linear. Two segments meet at a pivot, with C¹-continuous slope across the join (no piecewise kinks).

```
_ZOOM_PIVOT     = 1.0    # zoom value at the pivot
_PIVOT_T        = 0.6    # slider position of the pivot (0..1)
_PIVOT_SLOPE    = 0.4    # gentle near 1.0× — most zoom work happens here
_END_SLOPE_LOW  = 2.5    # zoom per unit slider at the floor
_END_SLOPE_HIGH = 12.0   # zoom per unit slider at the ceiling
```

The pivot at slider position 600 maps to zoom 1.0× — the resting "natural" zoom where the slider lives by default. Below the pivot, the curve descends gently into the zoom-out range so 60% of the slider's travel covers most of the meaningful zoomed-out altitudes. Above the pivot, the curve ramps faster into the zoom-in range — 5× zoom is reachable but takes deliberate slider travel.

The asymmetric design reflects how zoom is actually used: most navigation happens between 0.3× and 1.5×, the zoom-out band gets used for occasional aerial views, and zoom-in beyond 2× is rarer still. The curve gives the slider the most resolution where the user spends the most time.

`_slider_pos_to_zoom(pos)` is the forward map (called when the user drags the slider). `_zoom_to_slider_pos(zoom)` is the inverse, computed by 24-iteration bisection on the (monotonic) curve — called by `_sync_zoom_slider` after wheel zoom or Alt-drag zoom so the slider visually tracks the view's actual zoom value.

## Zoom-Aware Behaviours

Several systems on the canvas read `current_zoom` (or the painter's per-frame LOD) and adapt. Each lives at its own altitude and silently switches mode when crossed:

| System | Threshold | Adapts to |
|---|---|---|
| **Aerial paint** (`BaseNode.AERIAL_LOD_THRESHOLD`) | LOD < 0.15 | Skip chrome + paint_content + ports + selection chrome; paint a thin cream strip |
| **Wire paint** (`Connection._AERIAL_LOD_THRESHOLD`) | LOD < 0.15 | Skip the wire entirely — no Bezier evaluation, no glow segments |
| **Pulse gate** (`NodeBehaviour._PULSE_MIN_ON_SCREEN_PX`) | smaller_dim × zoom < 60 px | Pulse animation refuses to start; bg colour snaps directly without animating |
| **Media tiny-render** (`Scene._MEDIA_TINY_RENDER_PX`) | smaller_dim × zoom < 60 px | VideoNode pauses, AudioNode fades to silence |
| **Wire-snip tolerance** (`View._try_snip_at`) | always | Hit-test rect inflated by `10 / current_zoom` so click slop stays constant in screen pixels |
| **Shake-detect** (`BaseNode._detect_shake`) | always | Per-axis deltas multiplied by zoom before the threshold compare, so the same physical shake works at any altitude |
| **Scene auto-expansion** (`View._expansion_margin`) | always | Edge buffer = `viewport.width / 2 / zoom` so any edge node can be panned to centre at the zoom it was placed at |

The pulse gate, media tiny-render, and aerial paint cluster around the same altitude — roughly the point where a 400 px node renders at 60 px on screen, which lines up with LOD ≈ 0.15. That's the canvas's "altitude transition" — above it, individual nodes are a workspace; below it, they're map markers.

## Aerial Mode

Below `LOD < 0.15`, the canvas drops its entire interaction layer. The mental model is gameplay aerial view: zoom out to see where everything is, decide where to go next, swoosh back down. Concorde altitude — no need to read text or click ports up here, just shape recognition for navigation.

Concretely, three things happen below the threshold:

**Nodes paint as a thin cream strip.** `BaseNode.paint()` reads the painter's LOD via `QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())` and, below 0.15, replaces the entire paint pipeline with a single `fillRect` — a strip ~30% of the node's height, ~95% of its width, vertically centred, in `Theme.textPrimary` (cream). No chrome, no border, no body text layout, no ports, no selection ring.

The strip mimics what Qt's natural sub-pixel text rendering produces in this band: text-on-dark-body composites into a delicate cream line where text lives. The cheap `fillRect` reproduces that aesthetic at a fraction of the cost — no QFont, no word-wrap layout, no per-glyph rasterisation. The cost saving compounds: 8 node types use `Qt.TextWordWrap` for body content, and word-wrap re-runs layout at every paint, which means every zoom frame previously paid that cost across every visible node.

**Connections skip entirely.** `Connection.paint()` reads the same threshold (mirrored as `_AERIAL_LOD_THRESHOLD = 0.15` to avoid importing across the `nodes/`↔`graphics/` boundary) and returns early below it. Topology reads from node positions alone at this altitude — wires would just be visual noise on a map. The Bezier path evaluation across many wires per zoom frame was the second-largest paint cost behind word-wrapped text.

**Pulse and media gates already aerial-active.** These predate the aerial paint feature and stay active at the same altitude — pulse animations refuse to start, video/audio nodes pause. The new paint optimisation is the missing piece that completes the aerial-mode picture: every per-node ambient cost now drops in unison once the canvas crosses into navigation altitude.

### Why one threshold, not a band

A smooth fade between full paint and aerial paint across an LOD range was considered and rejected. The visual transition during interactive zoom is a single hard switch in one frame, which reads as a clean "altitude change" rather than a fuzzy shift. For screenshots — the original motivation for the feature — there is no transition at all, just the final image at the chosen zoom. A hard threshold also keeps the paint logic trivial: one comparison, one branch.

### Tunable parameters

| Knob | Location | Effect |
|---|---|---|
| `BaseNode.AERIAL_LOD_THRESHOLD` | `nodes/BaseNode.py` | Altitude at which nodes drop to strip. Raise = more paint cost, more visual fidelity at moderate aerial. Lower = less cost, cream strip kicks in only at deeper aerial. |
| `Connection._AERIAL_LOD_THRESHOLD` | `graphics/Connection.py` | Altitude at which wires drop. Currently kept in lockstep with the BaseNode value. |
| Strip height proportion (`0.3` of node height) | `BaseNode.paint()` inline | Bigger = more solid look, smaller = more delicate. |
| Strip horizontal padding (`8.0` px) | `BaseNode.paint()` inline | Affects how flush the strip sits to the node edges. |

The strip math is intentionally inline rather than abstracted — it's three lines and the geometry is obvious at the call site. If a per-node-type strip ever becomes desirable (different proportions for AboutNode vs WarmNode, for example), the natural extension is a method `_paint_aerial_strip(painter)` that subclasses override. Not needed yet.

## Technical Notes

- **`levelOfDetailFromTransform` reads the *painter's* current transform**, which is the composed scene→viewport scale at paint time. For an unrotated, unscaled item this equals `View.current_zoom`. Reading it from the painter rather than from the View is what keeps `BaseNode.paint()` free of any cross-object state lookup — no signal plumbing, no scene-level cache to invalidate, no per-paint dictionary read.
- **`<` and not `<=` at the threshold.** When `AERIAL_LOD_THRESHOLD == ZOOM_MIN`, strict `<` would never trigger at the floor and the aerial mode would be unreachable. The current `0.15` threshold sits comfortably above the floor, so strict `<` is correct — there is no edge case at the boundary.
- **The slider's `singleStep=10, pageStep=50`** means each arrow-key tap or scroll-wheel notch on the slider widget itself moves zoom by a non-trivial amount — the slider is for jumping between altitudes, not fine-tuning. Fine zoom adjustment lives in the wheel and Alt-drag channels.
- **`current_zoom` vs `transform().m11()`**. Both report the same value for unrotated items. `current_zoom` is the cached scalar and is preferred for any per-frame check; `transform().m11()` is read once during pan delta math (`mouseMoveEvent`) where the freshness of the live transform matters more than the cache.
- **Programmatic callers must use `_apply_zoom`**. Calling `view.scale(factor, factor)` directly bypasses the clamp and the `current_zoom` update — the slider would desync, the aerial threshold would still work (it reads from the painter, not from `current_zoom`), but every other zoom-aware system would be lying to itself. There is no scenario where direct `scale()` is correct outside of `_apply_zoom`'s body.

## Relationship to Other Systems

- **Pretty Widgets sliders** — `pretty_slider` is the shared slider widget. The zoom slider's vertical orientation, range, and step values are wired here; the curve is owned by `IntricateApp` because it is Intricate-specific. Other apps in the family that adopt the same slider style would supply their own curve, not inherit Intricate's.
- **Theme system** — `Theme.textPrimary` is the cream colour used for both the aerial strip and the natural body-text rendering it mimics. The strip stays visually consistent with full-paint mode through this single source. A theme change to text colour propagates to aerial mode automatically with no code edit.
- **Scene auto-expansion** — `_expansion_margin` reads zoom to compute a viewport-aware edge buffer. The buffer scales with zoom so an edge node placed at any zoom can later be panned into the viewport centre without scrolling against the scene rect. This is independent of aerial mode but shares the "zoom is the canvas's primary state" worldview.
- **Particle system** — particles inherit the painter's current transform and naturally scale with zoom. They do not currently aerial-gate, but the paint cost is bounded by the live particle count (capped well below the 200k physics budget — see the `feedback_reserve_discipline` memory) so the cost stays small even at full natural paint during zoom.
