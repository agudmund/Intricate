# Warm Splitter Hang Investigation

A diagnostic record of the "1,938-paragraph paste hung the UI until taskkill" symptom, captured 2026-05-08. The investigation phase was short — the latest session log carries the crime scene, and the missing protection is a clean omission from a known pattern (`scene._bulk_adding` quiescence + `processEvents` watchdog) that was wired into `load_session` and `import_session` but never extended to `chain_spawn`. This document is the artifact the diagnosis lives in; the next-steps ordering at the end is what the work continues from.

---

## The Symptom

- Pasting a multi-paragraph chunk of text into a WarmNode triggered the paragraph-aware splitter. The UI froze immediately and stayed frozen for ~13 minutes until the user forced `taskkill` to release it.
- No crash dialog. No fault.txt. No log message after the splitter announced itself. The process held the UI thread fully.
- The paste was substantial — but not pathological — content. It is on-spec for the splitter per the existing benchmark: *"Intricate is optimised to load 1200+ nodes in ~36 ms, so a thousand-paragraph paste is on-spec."* (`Documents/Nodes/The Warm Node.md`)
- The user's instinct on the regression range: *"the splitter took forever to run, which it shouldn't do even at that scale, we have previously benchmarked it at doing ca 1000 nodes in under a second."*

---

## The Crime Scene — `intricate_20260508-04.30.31.log`

Session loaded at 05:04:31 with the **Iconic** project — a populated scene of ~410 nodes:

```
[load] restored nodes  (864 ms total)
[load]   warm                288 × 1.31 ms = 379 ms
[load]   sticker              16 × 10.65 ms = 170 ms
[load]   palette               3 × 46.15 ms = 138 ms
[load]   about                86 × 0.94 ms = 81 ms
[load]   image                16 × 2.92 ms = 47 ms
[load] restored connections: 339  (68 ms)
[load] TOTAL load_session: 939 ms
```

The session loaded cleanly in under a second — the existing `_bulk_adding` quiescence around `load_session` did its job (288 + 16 + 3 + 86 + 16 = 409 nodes plus 339 connections, at ~36 ms aggregate node-construction time per the established benchmark, the rest being IO and warm-up).

22 minutes of normal work followed. Then the paste:

```
2026-05-08 05:26:31 - warmnode - INFO - [paste] text_len=411017 paragraphs=1938 safety_ceiling=20000 split=True
```

**That is the last entry in the log.** No `[scatter]` probe lines from `spiral_place`. No `[warm split] ... paste split into N chunks` completion line. No autosave events. No InfoBar fade events. No window-behind detections. The main thread was fully occupied from that point until the user issued `taskkill` 13 minutes later.

The shape — silent, total UI freeze, no progress markers — rules out crashes (would have left a fault.txt) and rules out a slow-but-progressing run (would have produced periodic log lines from the `[scatter]` debug, autosave debounce, or any other timer-driven channel).

---

## Hypothesis Buckets — The Three Possible Shapes

Before locating the fix, three candidate causes were enumerated, each producing a distinct expected shape against the log evidence:

| Bucket | Cause | Expected shape | Match? |
|---|---|---|---|
| **1** | Splitter input is pathological (a single 411 KB paragraph, hits the cascading-chunker fallback) | Long blocking inside `paragraph_chunks` before the spawn loop ever begins | **No** — the [paste] log line reports `paragraphs=1938`, which means `paragraph_chunks` already ran and returned. The freeze is downstream |
| **2** | Spawn loop is genuinely slow per-iteration on a populated scene + has no UI yield | Linear hang scaling roughly with `paragraphs × scene_population`, no log progress because no `processEvents` runs | **Yes** — fits the silence and the duration |
| **3** | Reentrancy / infinite loop somewhere in the spawn loop (e.g. `_on_text_changed` re-firing the splitter against itself) | Hang that doesn't depend on chunk count, would also have hit on smaller pastes | **No** — the splitter sets `_editor.blockSignals(True)` around the first-chunk write specifically to avoid this; smaller pastes work fine |

**Bucket 2 is the dominant shape.** The remainder of the document specifies why.

---

## Diagnosis — `chain_spawn` is missing the `_bulk_adding` wrap

The splitter at `nodes/WarmNode.py:594` hands the chunk list to `utils.placement.chain_spawn`:

```python
chain_spawn(scene, source_node=self, items=chunks[1:], factory=_warm_factory)
```

`chain_spawn` (at `utils/placement.py:319`) iterates the items and per item:

1. Constructs a node via the factory
2. Stages it offscreen via `setPos(OFFSCREEN_STAGING)`
3. Adds it to the scene (`scene.addItem(node)`)
4. Raises its z (`scene.raise_node(node)`)
5. Auto-fits title width and body height
6. Picks an organic origin (`wander_origin(prev_node)`)
7. Probes for a clear seat (`spiral_place` — up to 50 probes, each calling `scene.items(...)` for node-on-node and wire-path-clear checks)
8. Sets the final position
9. Constructs and adds a Connection

**There is no `scene._bulk_adding` counter raised around this loop, and no `processEvents()` yield between iterations.** Compare this to the two protected paths that wrap the same fundamental operation:

| Path | File:line | Protected? |
|---|---|---|
| `load_session` (file restore) | `graphics/Scene.py:1078` | ✓ `_bulk_adding` raised, `processEvents` yields every 10 nodes |
| `import_session` (paste/clipboard restore) | `graphics/Scene.py:1219` | ✓ same |
| `chain_spawn` (paragraph split / .py drag-drop / CushionsNode export) | `utils/placement.py:319` | ✗ **no protection** |

The three peer-paint sites that the gate is designed to short-circuit all already check it — they're ready and waiting:

- `nodes/NodeBehaviour.py:254-258` — pulse-value handler early-returns when `_bulk_adding > 0` or `_bulk_removing > 0`
- `nodes/NodeBehaviour.py:310-314` — bg-anim handler same
- `graphics/Connection.py:255-258` — connection paint handler same

The gate is wired. Two of three callers raise it. The third — `chain_spawn` — never does. Every paragraph spawn fires every existing peer's pulse animation tick and connection glide tick at full cost.

---

## Why The Benchmark Held But The Live Paste Didn't

The "1200 nodes in ~36 ms" benchmark is real and current, but it measures **`load_session` on a fresh scene** — a session-switch rebuild where the destination scene starts empty, so peer-iteration cost is zero on every `addItem`. The `_bulk_adding` quiescence is also live in that path, so even though the rebuild momentarily creates many peers, none of their NodeBehaviours pulse during the burst.

The paste-split runs in a fundamentally different regime:

| Variable | `load_session` benchmark | This paste |
|---|---|---|
| Initial peer count | 0 | ~410 |
| `_bulk_adding` raised? | Yes | **No** |
| `processEvents` yield? | Every 10 nodes | **None** |
| Items added | 1200 | 1938 (chunks) + 1937 (connections) = **3875 addItem calls** |

The naive cost expectation when porting the benchmark across regimes is *"~3875 / 1200 × 36 ms ≈ 116 ms"*. The actual cost is bounded by the per-spawn peer-animation perturbation (every existing peer's setScale tick fires during paint cascades), the spiral_place `scene.items()` probe loop (up to 50 probes × current scene population, growing per spawn), and the BSP rebuild on every `addItem`. None of those are on the critical path during `load_session` because the gate suppresses the first and the empty starting scene minimises the second.

Compounding cost across 1938 iterations, with no `processEvents` to yield the UI thread, produces the symptom: the splitter is in fact running, just at a wall-clock pace that exceeds the user's patience threshold by orders of magnitude, and the UI cannot paint or accept input until it returns.

---

## Mechanism Hypothesis

Per spawn, on a populated scene:

1. `scene.addItem(node)` triggers Qt's BSP-tree update for spatial indexing. The cost grows mildly with scene population
2. The new item's `ItemSceneChange` / `ItemSceneHasChanged` events fire — no peer cost on its own, but the scene change marks neighboring items dirty for the next paint
3. `setPos(OFFSCREEN_STAGING)` then `setPos(final)` each fire `ItemPositionChange` / `ItemPositionHasChanged`
4. `spiral_place` calls `scene.items(rect)` repeatedly. Each call iterates the spatial index in the queried region. With a populated scene and a probe loop, this is the largest single-iteration cost
5. `scene.addItem(connection)` adds another item, with the same ItemSceneChange cascade
6. Any peer with a live `bg_anim` or pulse animation continues to tick at ~16 ms intervals while the loop runs. Each tick fires `setScale` → invalidates that peer's paint region. Without `_bulk_adding`, those ticks aren't suppressed; the paint pipeline keeps dirtying and flushing across the entire chain run

Steps 4 and 6 are the dominant contributors. Step 6 is exactly what the `_bulk_adding` gate was added to suppress (per the 2026-04-21 89-node import hang); step 4 is independent and would benefit from a complementary BSP-scoped optimisation, but step 6 alone is sufficient to explain the freeze magnitude.

---

## Other Callers — Same Shape, Latent

`chain_spawn` is shared by three callers per the docstring and code search:

| Caller | File:line | Likely chain length | Status |
|---|---|---|---|
| `WarmNode._split_oversized_paste` | `nodes/WarmNode.py:594` | 0 to thousands (paragraph-driven) | **The bug being investigated** |
| `CushionsNode._export` | `nodes/CushionsNode.py:154` | 0 to thousands (paragraph-driven, same content shape) | **Latent** — same regression on a populated scene |
| `View.py` palette-on-py-drop | `graphics/View.py:592` | exactly 1 | **Harmless** — single spawn doesn't compound |

Fixing `chain_spawn` itself once covers all three.

---

## Mitigation Options

The diagnostic phase is closed. Three approach families for the fix, ordered by cost and yield:

| Approach | Cost | Yield | Notes |
|---|---|---|---|
| **Wrap `chain_spawn` with `_bulk_adding` + periodic `processEvents` yield** | Trivial — mirrors `load_session` and `import_session` exactly. ~10 lines in `utils/placement.py:chain_spawn` | Resolves the freeze for all three callers in one place | Aligns with the established pattern; the gate is already wired into the three peer-paint sites; the watchdog yield matches the load-session cadence |
| **Add a defensive gate at each call site** | Same effort, three places to maintain | Same yield, more surface to drift | Less maintainable — the canonical helper is the right home for the canonical pattern |
| **Optimise `spiral_place`'s probe loop independently** | Larger refactor (BSP-aware probe, possibly a candidate-set cache) | Partial — addresses step 4 of the mechanism, leaves step 6 untouched | Worth doing eventually, but the _bulk_adding fix is the load-bearing change. Don't blend the two |

The first option is the small, focused fix that resolves the symptom and matches established convention. Option 3 is a separate optimisation worth scoping later if `spiral_place` cost becomes visible after the gate is wired.

---

## Next Steps — Decided Order

1. **Document and accept** ✓ — *this document*. The diagnosis is captured while it is fresh; the omission is identified, the mechanism is explained, the precedent (`load_session` / `import_session`) is named.
2. **Wire `_bulk_adding` + `processEvents` into `chain_spawn`** — single-place fix in `utils/placement.py`. Mirror the cadence used by `load_session` (raise the counter on entry, lower it in `finally`, yield every N items). N=10 matches existing convention; could be tuned to N=20 since the per-spawn cost is heavier than per-load and yield frequency benefits from lower overhead-to-progress ratio.
3. **Verify** — re-run the 1,938-paragraph paste against the same `Iconic` scene, confirm: (a) the splitter completes, (b) the UI remains responsive (the curtain-perf hooks already capture this, the splitter's own `[warm split]` completion line confirms (a)), (c) the InfoBar whisper *"big paste split into 1938 nodes"* fires.
4. **Update `Documents/Nodes/The Warm Node.md`** — the existing line about benchmarked-on-empty-scene cost is correct, but worth a one-line note that the splitter's protection now lives in `chain_spawn` (the canonical place for the canonical pattern) rather than the splitter itself.
5. **Parked: `spiral_place` probe-loop optimisation** — only if probe-cost remains visible after the gate is wired. The dominant cost was the peer-animation perturbation; once that's quiet, the probe loop's actual cost should be measurable cleanly, and a remediation can be scoped against numbers rather than against a freeze.

---

## What's Ruled In / Ruled Out

**Ruled in:**

- Missing `_bulk_adding` quiescence in `chain_spawn` — the load-bearing omission
- Missing `processEvents` watchdog yield in `chain_spawn` — the secondary omission
- Compounded cost over a populated peer set (~410 nodes) for a long chain (1,938 items)

**Ruled out:**

- A regression introduced by recent commits — `git diff` against the gitStatus snapshot is empty (the dirty `BaseNode.py` / `ChromelessRoot.py` files were swept into `c4e4e16`/`de04043` between the snapshot and now); `chain_spawn` itself is unchanged on the relevant horizon
- The chrome-instrumentation TRACE work (`d5a10e8`) — those entries fire only for `ChromelessRoot` descendants (StickerNode et al), not WarmNode. No chrome-instrumentation noise in the spawn-time hot path
- Splitter input being pathological — `paragraph_chunks` returned 1,938 paragraphs, all under the 20,000-char ceiling per the [paste] log line; the cascading chunker never fired
- Reentrancy on `_on_text_changed` — the splitter `blockSignals(True)` on the editor around the first-chunk write specifically to avoid that path
