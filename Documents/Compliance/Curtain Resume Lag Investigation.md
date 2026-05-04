# Curtain Resume Lag Investigation

A diagnostic record of the "massive lag on the UI when I resume it after long durations of idle" symptom, captured 2026-05-04. Phase 1 instrumentation paid out cleanly — we have a measured shape, a bucket diagnosis, a threshold range, and a load-bearing user insight that reframes the threshold reading itself. This document is the artifact the diagnosis lives in; the next-steps ordering at the end is what the work continues from.

---

## The Symptom

- The very first curtain rolldown after a long idle stretch (overnight, or a multi-hour step-away) is visibly draggy and chunky compared to the same animation flipped repeatedly during active use.
- Total animation duration stays the same — the duration constant in `theme.curtains.up_ms` / `down_ms` is honoured. What changes is how the duration is *spent*.
- Subsequent curtains during the same active session are smooth.
- The lag is reproducible only after extended absence, never during active work.

The user's instinct on the cause range: "feels like a memory leak or something like that" — proposed Phase 1 as measurement-before-hypothesis to convert *"slow"* from a subjective adjective into objective per-frame numbers.

---

## Hypothesis Buckets — The Three Possible Shapes

Before instrumenting, three candidate causes were enumerated, each producing a distinct expected shape in the per-frame timing:

| Bucket | Cause | Expected shape |
|---|---|---|
| **1** | OS paging — Windows trims the working set during long idle; first touch causes major page faults reading code/data back from disk | Very slow first frame, fast rest |
| **2** | Cold caches — font metrics, painter caches, GPU shader cache, blur kernel cache, DWM compositor caches | First paint of a kind is slow, *and* sustained slowness across all frames of the animation |
| **3** | Backlog flush — timers, file watchers, animation engine waking with queued events that all fire on reactivation | Sustained slowness for several frames, then settles, with occasional isolated spikes |

The shape diagnosis from Phase 1 maps directly back to these buckets — see **Diagnosis** below.

---

## Phase 1 Instrumentation

Landed in commit `9975fbb` (`main_window.py`). Three small pieces wired around the existing curtain animation lifecycle:

1. **Instance state on `IntricateApp`** — `_curtain_perf_last_finished_t` (carried across animations to compute idle gap) and `_curtain_perf` (per-animation accumulator dict).
2. **Per-frame tick handler** — `_on_curtain_frame()` connected to the animation's `valueChanged` signal. Records ms-since-last-frame into a list. The *first* recorded delta is the time from `.start()` to the first frame — i.e. Qt animation engine startup cost, the most likely victim of cold caches.
3. **Settle digest** — `_on_curtains_settled()` extended to compute median, p95, max, total, gap-since-previous, and emit one `[curtains-perf]` log line per curtain.

Output format:

```
[curtains-perf] roll=<up|down> total=NNNms | gap=<seconds-since-last-curtain | "first-curtain"> | frames=N | first=Nms median=Nms p95=Nms max=Nms
```

Closure pattern — state lives on `self._curtain_perf` and is finalised in settle. The `curtain_anim` is recreated each toggle, so the `valueChanged` connection dies with it; no disconnect bookkeeping needed.

---

## Data Captured — 2026-05-04

Session log: `intricate_20260504-17.27.05.log` — process started 17:27:05, last write 19:35.

All nine curtain-perf events captured, in chronological order:

| # | Time | Gap | Frames | First | Median | p95 | Max | State |
|---|---|---|---|---|---|---|---|---|
| 1 | 17:33:12 | first-curtain | 35 | 29ms | 24ms | 71ms | 106ms | startup warm-up |
| 2 | 17:54:51 | 22 min | 43 | 13ms | 16ms | 48ms | 128ms | baseline (active) |
| 3 | 18:06:32 | 12 min | 43 | 7ms | 16ms | 47ms | 128ms | baseline (active) |
| 4 | 18:15:30 | 9 min | 43 | 7ms | 16ms | 47ms | 128ms | baseline (active) |
| 5 | 18:15:52 | 22 sec | 42 | 13ms | 18ms | 49ms | 128ms | baseline (active) |
| 6 | 18:17:43 | 2 min | 42 | 12ms | 16ms | 46ms | 114ms | baseline (active) |
| 7 | 18:43:00 | 25 min | 43 | 14ms | 16ms | 38ms | 129ms | baseline (active) |
| **8** | **19:32:04** | **49 min (walk)** | **15** | **99ms** | **54ms** | **110ms** | **110ms** | **POST-IDLE** |
| 9 | 19:36:34 | 4.5 min | 17 | 37ms | 47ms | 102ms | 102ms | partial recovery |

Raw format from the log:

```
[curtains-perf] roll=down total=911ms | gap=1517s | frames=43 | first=14ms median=16ms p95=38ms max=129ms        # line 7 — last baseline before walk
[curtains-perf] roll=down total=949ms | gap=2943s | frames=15 | first=99ms median=54ms p95=110ms max=110ms      # line 8 — first curtain after walk
[curtains-perf] roll=down total=914ms | gap=268s  | frames=17 | first=37ms median=47ms p95=102ms max=102ms      # line 9 — second curtain after walk
```

All nine events are `roll=down` (expand from collapsed strip to full canvas) — the user's normal interaction pattern is to leave curtains UP during idle stretches and roll DOWN to interact, so the rolldown is the operation that pays the recovery cost.

---

## Diagnosis

| Signal | Baseline | Post-walk (line 8) | Ratio | Bucket signature |
|---|---|---|---|---|
| First-frame | 13–14 ms | **99 ms** | **~7×** | **Bucket 1** — paging / cold cache hit on the first frame |
| Median | 16 ms | **54 ms** | **~3.4×** | **Bucket 2** — sustained cold paint pipeline across *all* frames |
| Max | 128 ms | 110 ms | similar | **NOT Bucket 3** — no GC pauses, no event-flush spikes |

**Bucket 2 dominant, Bucket 1 contribution on the very first frame.** The whole paint pipeline is cold, and the first frame additionally pays a paging cost. GC and event flush are ruled out cleanly — max stays normal across the run, no isolated outliers.

---

## Frame-count Translation

Same wall-clock duration both runs (~900–950 ms target hit), but the frame count tells the visible story:

| Run | Frames | Duration | Effective rate |
|---|---|---|---|
| Baseline (active) | 42–43 | 900 ms | ~47 Hz |
| Post-walk (line 8) | **15** | 949 ms | **~16 Hz** |

Frame count dropped 65%, total time barely moved. Qt's animation engine ticks at "wall clock" not "frame target" — when each frame paint exceeds the budget, frames get skipped to land the animation on time. The eye registers a 16 Hz animation as chunky/draggy/heavy, even at the same total duration. *That* is what the user perceives as "slow".

---

## Recovery Curve

Recovery is gradual, not instant. Line 9 (the next curtain, 4.5 min after line 8) shows partial recovery:

| Signal | Line 8 | Line 9 | Recovered |
|---|---|---|---|
| First-frame | 99 ms | 37 ms | **~60%** (paging mostly came back) |
| Median | 54 ms | 47 ms | **~13%** (paint pipeline still cold) |
| Frames | 15 | 17 | minimal |

A single curtain interaction is **not enough** to fully warm the system back. The paging cost is mostly recovered by interaction #2, but the broader paint-pipeline cost persists. Mapping the full recovery curve (lines 10–12) was not captured this session and is captured as future work below.

---

## The Threshold and the Pulse-as-Warmer Hypothesis

The cleanest finding in the dataset:

- **25-min gap** (line 7): fully baseline — 43 frames, 16 ms median
- **49-min gap** (line 8): severely degraded — 15 frames, 54 ms median

A naive read places the threshold somewhere in 25–49 min. But the user's session log reveals a structural difference between those two gaps that reframes the threshold reading entirely:

> *"The difference between the 25-minute gap and the 49-minute gap is I was away during the 49-minute gap while the 25-minute gap I kept it fed during, it never went idle and hungry. I suspect the actual pulse animation on the UI to be a factor in why these two gaps are different in behaviour."* — user, 2026-05-04

This is load-bearing. Hover pulses fire only on cursor proximity to nodes — `NodeBehaviour.on_hover_enter` triggers the pulse animation, which then drives `setScale` ticks every ~16 ms for the breath duration. An *active* user moving the cursor across a populated canvas keeps the paint pipeline busy continuously. An *absent* user, even with the app running, produces zero hover events, and the only ambient paint activity is whatever fires on internal timers (Meov whisper every 10–15 min, joy/sleep ticks, infobar fades — all small and infrequent).

The reframed reading: **the threshold is not "elapsed time" but "elapsed time without paint activity"**. The 25-min gap had continuous paint activity (active user); the 49-min gap had near-zero paint activity (away user). DWM and Windows working-set policy operate on inactivity at the paint/GPU level, not on wall-clock — so an active user never crosses their threshold, regardless of session length.

This sharpens the remediation hypothesis substantially — see **Next Steps**.

---

## What's Ruled In / Ruled Out

**Ruled out:**

- GC pauses — would show isolated max spikes against healthy median; we see uniformly elevated median, no isolated outliers
- Event-flush backlog — would show stutter for first several frames then settle; we see uniformly elevated cost across the entire animation
- Code-side accumulation (signal connections, growing caches, leaked references) — wrong shape; would compound across active session, not selectively appear after absence

**Ruled in:**

- OS-level cold-pipeline cost
- Working-set paging on the first frame (Bucket 1 contribution)
- Cold paint / compositor caches across all frames (Bucket 2 dominant)
- The user's setup hits the trifecta DWM aggressively trims for: `FramelessWindowHint | WindowStaysOnTop | WA_TranslucentBackground`

**Ambiguous (Phase 2 would discriminate):**

- Working-set trim (memory cold) vs. DWM compositor idle (graphics cold) — both produce this shape. Distinguishing them takes the RSS + GC + animation-count heartbeat from Phase 2. Discrimination only matters if remediation requires it.

---

## Mechanism Hypothesis

Windows DWM (Desktop Window Manager) suspends compositor work for inactive frameless+translucent windows after an idle period, and the OS working-set trimmer reclaims pages from inactive UI processes on a similar timescale. Both thresholds typically sit in the 30–60 min range for processes that aren't producing paint output. When the curtain animation kicks in after a long absence:

1. **First frame** — page faults read trimmed code/data pages back from disk, plus the paint pipeline rebuilds caches (font metrics, brush cache, painter state) on first use → 99 ms cost
2. **Subsequent frames** — DWM compositor warming up, GPU shader cache rebuilding, blur kernel cache cold → 54 ms median sustained across the rest of the animation
3. **The animation engine** — fixed wall-clock duration, drops frames to fit → 15 frames instead of 43

Active paint activity (hover pulses driving `setScale` repaints continuously across the populated canvas) keeps DWM busy, keeps the working set referenced, and keeps the paint pipeline caches warm. Absence of that activity is what crosses the trim threshold.

---

## Next Steps — Decided Order

User-confirmed sequencing 2026-05-04:

1. **Accept and document** ✓ — *this document*. The Phase 1 mission of "decipher what slow means and articulate it" is now complete; the diagnosis is captured while it's fresh and undisputed.
2. **Try remediation directly** — the pulse-as-warmer hypothesis is testable and points at a specific mitigation: a periodic tiny paint nudge during prolonged collapsed-state absence, sized to match the natural pulse-tick cadence. If a small ambient repaint every N minutes during curtains-up keeps DWM warm without measurable battery cost, the symptom resolves without needing Phase 2's sub-bucket discrimination.
3. **Phase 2 only if needed** — RSS / GC / animation-count heartbeat snapshot CSV. Run only if the remediation in step 2 fails or has unexpected side effects, to discriminate working-set trim (memory cold) from DWM compositor idle (graphics cold) and target the fix more precisely.

The reversed order (relative to my initial proposal) is the right call: documentation locks in what we know now while subsequent steps risk forgetting; remediation is hypothesis-test on a strong specific lead; Phase 2 is fallback discrimination only if the strong lead doesn't pan out.

---

## Future Work (parked, not blocking)

- **Map the full recovery curve.** Capture lines 10–12 (continued curtain interactions after a long-idle event) to see how many curtains it takes to fully return to baseline. The 4.5-min sample we have shows partial paging recovery + minimal paint-pipeline recovery — would expect full convergence within 2–4 more interactions, but this is unmeasured.
- **Capture a `roll=up` baseline.** All nine events captured were `roll=down`. The collapse direction may have a different shape (fewer paint dependencies — the strip is rendering less). Worth a sanity check, low priority.
- **Test the pulse-as-warmer hypothesis cleanly.** Reproduce the symptom with a controlled experiment: curtains up + machine awake + no cursor movement for 50 min, then trigger curtain. Compare to: curtains up + cursor making small periodic motions to keep pulses firing on visible nodes for 50 min, then trigger curtain. If hypothesis is correct, the second condition shows baseline numbers.
