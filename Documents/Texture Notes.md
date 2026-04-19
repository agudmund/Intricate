# Texture Notes

Intentional design decisions that look like bugs if you don't know they're decisions.

This file exists because some features can't be captured in changelogs. *"4-stop asymmetric pink gradient on text selection"* means nothing as a bullet point — the effect only appears during the gesture of using it. When future-you touches the code that implements one of these and thinks "I should clean this up," this file is the note that says: it's load-bearing, here's what it's doing, here's how to recognise the feeling if it regresses.

Append-only. Entries never leave, because the features they describe don't either.

---

## The Ink-Drying Text Selection

**What it looks like.** Drag-to-select in any PrettyEdit (AboutNode, WarmNode, ClaudeNode input, etc). The selection highlight is a gradient, not a flat block. As the selection widens under your cursor, the bright leading edge stays pinned to your cursor tip while the dark trailing pool stretches back toward the start of the selection. The feel is of placing ink and watching it settle. At short selection widths the gradient compresses into a single confident mark; at long widths the trailing pool stretches into visible territory. The palette is width-responsive without a single line of code caring about width.

**How it works.** The 4-stop gradient is defined once in `PrettyEdit.py` and painted in the widget's own `paintEvent`. Qt's default selection highlight is made invisible by setting `QPalette.Highlight` to `QColor(0,0,0,0)` — that's intentional, don't restore it.

```python
self._sel_stops = [
    (0.0, QColor("#1e1e1e")),   # dark base
    (0.4, QColor("#5c3e4f")),   # muted rose
    (0.7, QColor("#a56a85")),   # warm mauve
    (1.0, QColor("#d87a9e")),   # bright pink
]
```

The stops are **deliberately non-linear.** Evenly spaced (`0.0, 0.33, 0.66, 1.0`) would produce three equal transitions and feel uniform. The `0.4` stop weighs the first two-fifths of the selection as a slow dark-to-rose pool; the final 60% moves through two shorter transitions to bright. Heavy trailing edge, quicker brightening ahead. That asymmetry is what produces the "wet" feeling at distance — at long selection widths, the stops physically separate in space and the gaps between them become features rather than transitions.

**Why it feels like motion.** The gradient is parametrised `0.0 → 1.0` relative to the selection rect. You're not animating the gradient — you're animating the container. As the rect widens during drag, the bright stop stays at the cursor tip and the dark stop stays at the start of the selection, with the mauve midtones stretching across the distance between them. The motion is emergent from a completely static specification.

**If this regresses.** Check that `QPalette.Highlight` is still transparent and that the custom `paintEvent` is still drawing the gradient path under selected text. Flat highlight back = custom paint path has been bypassed or the palette has been restored to defaults somewhere.

**Originality note.** Known prior art: rounded-corner selections (Google Docs, iOS), semi-transparent block overlays, syntax-aware multi-colour highlights, cursor-trail animations on the cursor itself. Width-responsive gradient selection that behaves like settling ink — not known to the author elsewhere. If you find prior art, name it honestly here; otherwise this is an original invention.

**Shared vocabulary.** The 4-stop gradient is the canonical "progress bar look" across the entire app family. It also paints the joy bar on the Intricate sidebar, the video scrub bar on VideoNode, the volume slider, and any future progress indicator. Text selection is the same palette in a different role. Keeping these in lockstep is deliberate — changing the gradient stops in one place means changing them everywhere, because the shared vocabulary is the point. See `CLAUDE.md § Progress Bar Gradient` for the canonical stop definitions.

---

## Selection Line Height — The Glyph Silhouette Hugger

**What it does.** `Theme.aboutHighlightTrim` (controlled via `[node.about] highlight_trim` in `settings.toml`) is a per-font vertical compensator. It adjusts the painted selection rectangle's height independently of the font's *declared* line metrics.

**Why it exists.** Fonts lie. Every font has an official bounding box — `QFontMetrics.height()` — that tells Qt how much vertical space to reserve. But the *visual* footprint of the glyphs inside that box is often much smaller, especially in italic display fonts with decorative ascenders. Paint the selection highlight at the full declared height and you get a pink wall towering around a small italic word. Crop it by hand and you get a tight highlighter that hugs the actual glyph silhouette instead of the font's declared bounding box.

**Why it's per-font and not algorithmic.** Chandler42 wants roughly `-10`. Any other font will want its own number, discovered by eye, not calculated. There's no formula — it's a visual relationship between a particular font's declared metrics and its particular glyph shapes. Switch fonts, re-tune.

**How to tune it.** Open an AboutNode or WarmNode, select some text, look at it. If the selection bulges above or below the glyphs, make the number more negative. If the selection crops into the glyph tops or tails, make it less negative. It's a 30-second tune with the Settlers slider. Screenshot the result if you're proud of it.

**If this regresses.** Check that PrettyEdit's custom `paintEvent` is still offsetting the selection rect by `Theme.aboutHighlightTrim`. If the selection jumps back to fill the full declared line height, the offset has been lost somewhere in the paint pipeline.

---

## The Draggable Colour Swatch

**What it does.** The hex colour swatches in the Settlers UI (the three-up rows under every `[node.xxx]` section — `bg_color`, `bg_color_front`, `text_color`) are draggable. Mouse down on a swatch, drag up to lighten, drag down to darken. Hue and saturation stay put; only HSL lightness shifts. The swatch, the hex field, and the field registry all update live during the drag.

**Why it exists.** For extended colour work, Photoshop and color.adobe.com remain the right tools — this isn't a replacement for those. It's the quiet nudge that lives where you're already looking, for the moment when you've picked `#2a3a2f` and realise it wants to be a hair brighter. Reaching for a full colour picker for a three-hex-point shift breaks the flow of looking at the actual thing you're tuning. A gentle drag on the swatch itself keeps attention on the result.

**How it feels.** Cursor turns into an open hand when you hover over a swatch — the affordance is visible before you touch it. Closes into a grabbed hand during the drag. Releases back to open hand on mouseup. The sensitivity is `1.5 px per HSL-lightness unit` (lightness is 0–255 in Qt), tuned so that a 100 px vertical drag spans roughly two-thirds of the full range — deliberate, not twitchy.

**Alpha preservation.** Input hex values of the `#RRGGBBAA` form stay 8-digit on the way out; `#RRGGBB` stays 6-digit. The drag touches only lightness. This matters for any colour with a carefully-tuned alpha that was painstakingly drag-dialled at some earlier point.

**If this regresses.** Check that `_DraggableSwatch` is still being used in `_add_swatch_cell` (in `The Settlers/main_window.py`) instead of a plain `QFrame`. If swatches have gone back to being inert, someone has flattened the class back out.

**Originality note.** Direct-manipulation colour pickers exist (Figma's on-canvas hue wheel, Adobe Colour's swatch tiles). Vertical-drag-for-lightness on the swatch itself, as the primary interaction, without exposing a wheel or a slider, is the specific texture here. Known elsewhere: probably somewhere, but not a pattern the author has encountered in config panes specifically. The gentleness is the point — no ruckus, no extra chrome, just a quiet touch.

---

## AboutNode — The Resize-Coupled Button Shelf

**What it does.** AboutNode is the only node type in the family where the button shelf is revealed and hidden by *resize direction* instead of a click-based toggle. Dragging the resize handle to make the node **taller** glides the shelf in (with a fresh More Glory emoji each time). Dragging to make it **shorter** glides the shelf out. Width-only adjustments leave the shelf alone. There is no click-to-toggle, no invisible hit-zone, no modifier key — the gesture IS the state machine.

**How it works.** `AboutNode.mouseMoveEvent` defers to `BaseNode.mouseMoveEvent` first (so the resize math runs and `self.rect()` reflects the new geometry), then checks `self.rect().height() - self._resize_start_rect.height()`. If the delta exceeds `_RESIZE_SHELF_THRESHOLD` (5 px) in either direction and the shelf state is the opposite of the delta's implication, `_toggle_shelf()` fires. The threshold is what prevents sub-pixel tremor from flipping the shelf twitchily.

The reveal path additionally calls `_reshuffle_emoji()` before toggling, so the More Glory button displays a different emoji every time the shelf surfaces. The hide path does not reshuffle — the shuffle is about the arrival, not the departure.

**Why this is AboutNode-only.** The other 30+ node types each have their own toolbar chassis baked in — big bodies, structural space, natural hit-zones for button strips. AboutNode is different: it is a sticky-note minimalist, a slap-on label that wants to stay empty of visible chrome the vast majority of the time. Forcing it to use the same top-strip-double-click reveal that works fine on the bigger nodes crushed its visual register — the top-strip had to be tall enough to be a comfortable hit-zone, which made the node feel unbalanced, and the bottom padding was then compensated-up to mirror the excess, which compounded the over-padded feel. **The node was being forced into a general pattern that didn't fit its material.**

The resolution principle, stated as-written during the redesign:

> *Consistency is a default, not a law. General patterns are where you start; specialisation is warranted where the material demands it. Forcing unique material into a general pattern crushes what made it worth having.*

AboutNode earned its bespoke interaction model because its material (minimalist sticky-note, used frequently, wants to stay chromeless) demanded different treatment from the other 30+ nodes (bigger chassis, toolbar-appropriate, consistent model works).

**The decoupling move — visual top vs interactive top.** The original problem was a single variable doing two jobs:
- *Visual*: the px gap above the glyph (breathing room for the typography)
- *Interactive*: the hit-zone that used to trigger the shelf-reveal on double-click

These two jobs wanted different sizes — visual wanted 2 px (tight, balanced), interactive wanted 15–20 px (comfortable hit target). Neither size satisfied both. The breakthrough was realising these jobs could be *decoupled* — move the interactive trigger off the top strip entirely (to the resize gesture), freeing the visual strip to shrink to whatever looks right typographically. Once decoupled, the top strip became a pure typography decision, no longer entangled with hit-zone requirements.

This is generalisable: **any UI element doing two jobs should be audited for whether those jobs want different dimensions.** If they do, decoupling is almost always the right move.

**The class-attribute override pattern.** `BaseNode._HIDDEN_TOP_OFFSET = 8.0` is the general default (the amount of top margin when the shelf is collapsed). `AboutNode._HIDDEN_TOP_OFFSET = 2.0` overrides it for this one node type. The hardcoded `8.0` that used to live inline in `BaseNode.__init__` and `BaseNode._toggle_shelf` was replaced with `self._HIDDEN_TOP_OFFSET`, which means any other node type that wants a tighter or looser collapsed offset can override the same way without touching `BaseNode`. Pattern, not magic number.

**The shake-resize gestural rhyme.** An unplanned alignment that emerged from this redesign: the shake-to-delete mechanism on all nodes is a *"wiggle vigorously in multiple directions"* gesture, and the resize-to-toggle-shelf on AboutNode is a *"pull in one direction"* gesture. Both are pull-responsive — the node reacts to being physically manipulated rather than to clicks. This wasn't designed in; it happened because both features separately honoured the creature-register (node-as-living-object that responds to touch) and the gestural vocabulary happened to rhyme. That's the signature of coherent interaction design: when you solve each piece honestly in its own terms, the pieces start to rhyme with each other without being forced.

**The bottom-padding compensation, removed.** The old `_auto_expand` formula used `doc_h + top + padT + 6` for the new node height — the `+ 6` was a temporary mirror added to balance the excessive top, producing symmetric-but-over-padded spacing. Once the top was tightened to 2, the mirror was trimmed to `+ 2` to match. Tight symmetric on both ends. If multi-line AboutNodes ever feel cramped, the `+ 2` can be tuned per line count — but so far the natural line-spacing between wrapped lines gives them enough breathing room that no special-casing is needed.

**If this regresses:**
- Shelf reappears on every resize including shrink-to-tidy → `mouseMoveEvent` has lost the bidirectional check; the hide-on-shrink branch is gone.
- Top strip has become generous again → either `_HIDDEN_TOP_OFFSET` was reset, or someone restored a hardcoded value in `BaseNode`.
- Shelf reveals on width-only resizes → someone switched from height delta to width delta or area delta; revert to height-only.
- Double-clicking on a visible shelf enters edit mode unexpectedly → the guard in `mouseDoubleClickEvent` (the `if self._buttons_visible and event.pos().y() < self._BUTTON_ZONE_H` check) was removed.
- No More Glory emoji reshuffle on reveal → `_reshuffle_emoji()` call was dropped from the grow-direction branch; restore it (but NOT on the hide path — shuffle is arrival-only).

**Originality note.** Resize-coupled shelf state, in the specific sense of "resize direction drives a bistable UI state machine," is not a pattern the author has encountered elsewhere in desktop apps. The closest analogues are (a) expandable/collapsible panels in IDEs where dragging a splitter past a threshold snaps the panel open/closed, and (b) window managers that snap to full-screen when dragged to the edge. This is different: the node stays fully responsive throughout the resize and only the *direction* of the resize (past a small threshold) determines the shelf state. If prior art exists, name it honestly here; otherwise this is an original interaction.

---

## Wire-Aware Scatter Placement

**What it does.** When a chain of nodes is spawned — from a MarkdownNode split, a WarmNode auto-split, a CushionsNode unpack, anywhere `utils/placement.spiral_place()` is used — each new node's position is chosen not just to avoid landing on an existing node, but also to avoid having its *wire-to-parent* cross over an unrelated node. Wires are allowed to cross other wires; that's fine. What's rejected is a wire that runs over a node that isn't its own endpoint, because that reads as rude overlap rather than clean flow.

**How it works.** `spiral_place()` accepts an optional `parent=None` argument. When supplied, after each candidate seat passes the node-on-node collision check, a second check runs:

1. Pick the parent's output port and the (hypothetical) new node's input port using the **same** `closest_output_port` / `closest_input_port` functions the live wire uses in `graphics/Connection.py` — the mechanism that decides which of the 8 ports the wire hooks onto as nodes drift. Reusing the exact picker means the scatter check agrees with the actual wire that will be drawn.
2. Treat the port-to-port straight line as a thin rectangle of width `wire_padding` (default 18 px — enough to absorb the bezier's heart-swell without being exact).
3. Narrow the scene query to items whose bounding rect intersects the segment's inflated bbox (cheap AABB prefilter).
4. For each unrelated node in that set, run a proper segment-vs-rect intersection test (CCW-sign trick against the 4 dilated edges, plus endpoint containment for early accept).
5. If any unrelated node crosses, reject the seat — the spiral moves to the next probe.

The check is approximate by design. A proper bezier trace would be more accurate but far more expensive, and the padded raycast is correct enough for a probe loop that runs up to 50 times per placement.

**Why the secondary effect matters more than the stated goal.** The original motivation was cosmetic — prevent wires from running through unrelated nodes. But the check does something larger: it rejects seats that are in densely packed regions (because those are exactly the regions where wires to parent must cross other nodes), which pushes the search outward into emptier space. The net effect is **spatial airiness without directional bias.** Random-sample-of-uncertainty stays intact as the organic signature — we just added one more criterion, and the whole chain started breathing. The tangle-stacking failure mode that plagued dense chains before this change resolved itself without a single line of deterministic bias.

**Why directional bias was deliberately NOT added.** A candidate-ordering bias (prefer angles near the parent→wander-origin axis) would have been a simpler-sounding fix. It was explicitly rejected because *the swaying back-and-forth of the random probe* is what makes the scatter feel alive instead of excel-like. Directional bias produces uniformity; uniformity reads as mechanical; mechanical breaks the creature-register the whole app lives in. If you're ever tempted to add directional bias to "clean up" the placement, **don't.** The randomness is not noise — it's the signature.

**Graceful failure.** In tight canvases, no seat may clear both checks within the `max_attempts=50` budget. The algorithm tracks a reserve: the first candidate that passes node-collision but fails wire-check. If all 50 attempts exhaust without a clean seat, the reserve is used — the node lands in a valid position and its wire runs over a neighbour, accepting the overlap honestly. Reads as *a choice made under duress* rather than corrupt layout. The user's term for it: *"expressional overlaps."*

**Port-picker reuse as an architectural virtue.** Both the live wire (as it glides during node drift) and the scatter check use the same `closest_output_port(ref)` / `closest_input_port(ref)` functions. This means the scatter's "which side will the wire come out of?" prediction is exactly what the live wire will do once drawn. No drift between prediction and reality. If you add or rename these port-picking methods, update both call sites together.

**Logging instrumentation.**
- `TRACE` level (`_log.log(5, ...)`) — per-probe position, for forensic debugging of pathological cases
- `DEBUG` level — per-placement summary: `"[scatter] WarmNode placed after 7 attempts, radius=340"` or `"[scatter] AboutNode gave up after 50 attempts, using wire-crossing seat"`
- All key `[scatter]` prefixes for easy grep

Future tuning of `max_attempts` should be data-driven from these logs — if 95% of placements resolve under 20 attempts in practice, the budget can safely be reduced.

**If this regresses:**
- Chains start showing tangled wires running through unrelated nodes again → the `parent=` argument isn't being passed by callers, or `_wire_path_clear` is returning True unconditionally.
- Placements become slow or laggy on busy canvases → someone removed the `scene.items(seg_bbox)` bbox prefilter and the wire-check is iterating every item in the scene.
- Chains start looking uniformly distributed in a single direction → someone snuck directional bias into the candidate generator. **Revert.** The randomness IS the feature.
- Scatter never places nodes even in empty canvases → the port-picker reuse broke (likely `closest_output_port` was renamed on one side without updating placement.py).

**Originality note.** Collision-based placement algorithms are well-known (the spiral-outward base was already a common pattern before this change). Wire-path-aware placement — where the *connection that will be drawn* is considered during placement — is less common; most node editors place first and re-route wires later, or accept crossings as part of the output. The specific design choice of rejecting *node-crossing wires* while allowing *wire-crossing wires* reflects a visual-grammar distinction (a wire over another wire is a clean-reading intersection; a wire over an unrelated node is read as ownership confusion). If prior art uses this exact criterion, name it honestly here; otherwise the combination is original.

---
