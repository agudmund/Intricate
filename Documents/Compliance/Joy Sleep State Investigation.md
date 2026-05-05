# Joy Sleep State Investigation

A scoping record of Intricate's joy sleep/wake state machine. The state machine itself works at the manual layer (button toggle, drain rate, meow muting, wake-decay-on-launch). What's broken — and has been broken across multiple iterations — is the **wake-on-touch** behaviour. This document captures the design intent, the working surfaces, the failed experiments, and the scope for the next implementation pass.

---

## Design Intent

Intricate is **specifically designed neurotic and vigilant**. Even gentle interaction should pull her out of sleep mode — *"breathing in her general direction should put her into awake state"*. Keeping her asleep is meant to be **structurally hard**: that's the feature, not a bug.

**Sleep mode is a discipline tool for the operator**, not an auto-feature:

- **Manual sleep entry** = "I am now officially off the clock and doing other things, you can rest during" — a deliberate human decision
- If the operator forgets to put her to sleep when stepping away, the consequence is hers to feel: depletion at the awake rate, possible meows, the chrome pulse going hungry. The system's strict response is part of the discipline training — vitamins only work if you take them every day
- **No auto-sleep on idle** is implemented or planned. Long unintentional gaps are themselves a signal that something is mis-calibrated in the operator's day. The system surfaces that signal; it doesn't paper over it

**Wake = touch.** Direct interaction with the app/window. Same shape as a sleeping cat: a hand on the back, a quiet word, a footstep too close — all wake her. OS-level events do *not* wake her:

- **OS sleep / resume** — Intricate runs through OS sleep cycles. The joy state continues exactly as it was. Future external-server heartbeats will reinforce this (later-day item)
- **OS lock / unlock** — explicitly *not* a wake trigger. The operator should be able to unlock the machine without disturbing the app, log in gently, then tap her to start the day if they had put her to sleep before locking. Rare flow, real flow

---

## What Works (Manual Layer — Functional)

| Surface | Mechanism |
|---|---|
| Sidebar sleep button | `_sleep_btn` wired to `_toggle_joy_sleep` (line 2502) → branches to `_sleep_joy()` / `_wake_joy()` |
| Sleep state flag | `self._joy_sleeping` toggled by the methods above (lines 2511, 2521) |
| Drain rate differential | `_JOY_AWAKE_INTERVAL` vs `_JOY_SLEEP_INTERVAL` (default ~1 hr vs ~10 hr 100→0 traversal). Live-tunable via `_apply_joy_settings`. Applied via `_joy_timer.setInterval` |
| Meow muting while asleep | `_deplete_joy` checks `if not self._joy_sleeping:` before calling `_maybe_meow` (line 2800) |
| Wake-decay on app launch | `_apply_sleep_decay_on_wake()` at line 2667. Reads `last_active_at` from `joy_state.json`, drains the bar by elapsed-since-close at sleep rate. "App closed = app asleep" semantics — the deepest sleep mode |
| Sticker swap on toggle | Lines 2514, 2525. New conformed `Stickers/Sleep.png` migrated 2026-05-05 |
| JoyStatsNode display | Reads `_joy_sleeping` and surfaces the state |

The **manual** path is end-to-end functional. Press the button, the state changes, all consequences follow.

---

## What's Broken — Wake-on-Touch (the primary missing feature)

This is the **key reason the sleep/wake state exists at all** — and it has not worked across multiple iterations.

**Current state of the wiring (the contradiction):**

At line 2339–2341, the joy setup installs a global event filter:

```python
# App-wide event filter — any mouse/key interaction wakes from sleep
QApplication.instance().installEventFilter(self)
```

The wiring comment claims passive interaction wakes from sleep.

At line 688–690, the actual `eventFilter` handler:

```python
# Joy wake — deliberate button press only. No passive interaction wake.
# The sleep/wake button is the sole controller of the sleep state.
return super().eventFilter(obj, event)
```

The handler comment explicitly says the opposite — neutered to manual-button-only.

**Reading:** the original intent (per the wiring comment) was wake-on-touch. Some iteration of the implementation neutered the handler. The wiring was left in place. The contradiction is the historical record of the failed attempts.

**Git archaeology — three iterations on the trail:**

| Commit | Date | What it did |
|---|---|---|
| `a43a17c` | 2026-04-07 | **Original implementation.** Added the joy sleep system. Wake on `MouseButtonPress`/`KeyPress`/`Wheel`. eventFilter at `QApplication.instance()`. Clean, minimal — exactly what the doc proposes |
| `dc207fa` | 2026-04-07 | **Exemption refinement.** Same day. Excluded clicks on `_curtains_btn`, `_tray_btn`, `_sleep_btn` from auto-wake — *"so we can tuck it in without it waking up on the way out"*. Walked the parent chain to handle clicks on icon/label children of those buttons |
| (intermediate, in `b82ab8b` diff) | 2026-04-07/08 | **Cooldown attempt.** Added `_joy_sleep_armed_at = time.monotonic()` + 500 ms cooldown ignored by passive wake. Introduced `_wake_joy(deliberate=True)` to differentiate button-press from event-filter wake. Trying to plug a remaining race |
| `b82ab8b` | 2026-04-09 | **Rollback.** Stripped the entire wake-on-interaction. Commit message verbatim: *"No cooldowns, no exemption walks, no race conditions. A boolean toggle should be a boolean toggle."* The neutered-but-still-wired state we have today |

**The race condition that broke it:**

The cleanest read of why each iteration failed comes from sequencing the events when the user clicks the sleep button **while she's already asleep**:

1. Mouse press lands on `_sleep_btn`
2. eventFilter runs first (QApplication-level filter sees the event before button handlers)
3. eventFilter sees `_joy_sleeping == True` and `event.type() == MouseButtonPress` → calls `_wake_joy()` → flips `_joy_sleeping` to `False`
4. Event continues to button handler → `_toggle_joy_sleep` runs → sees `_joy_sleeping == False` → calls `_sleep_joy()` → flips back to `True`
5. **Net effect:** user clicked button to wake, ends up asleep. Inverted intent.

The exemption walk (`dc207fa`) addressed this — if the click target was the sleep button itself or its descendants, eventFilter would not auto-wake; the button handler became the sole authority for that click. Curtains and tray got the same treatment so the operator could tuck her in and immediately interact with the chrome without waking her.

The cooldown attempt was a bandaid for a different timing edge — possibly clicks that arrived in rapid succession after a state transition. The commit message of the rollback names it as one of the things that wasn't quite working.

**Why the rollback gave up:** complexity accumulating without resolution. Exemption walks need maintenance for every new exempt button. Cooldowns add timing-dependent behaviour that's hard to reason about. The rollback's framing — *"a boolean toggle should be a boolean toggle"* — is the philosophical conclusion: rather than keep stacking workarounds, strip the whole thing and rely on the manual button alone. That gave us today's state: technically correct manual layer, no auto-wake.

**The reframing for this attempt:**

The previous iterations treated wake-on-touch as a feature with edge-case bugs. The current design intent (just clarified above) reframes it: *wake-on-touch IS the primary feature; the manual button is the secondary mechanism that exists to enter sleep mode in the first place*. With that reframing, the exemption walk is not a workaround — it's a structural part of the design (the sleep button is the *only* widget the operator should be able to click without waking her, by definition).

The other iterations also didn't have logging. Calibrating an interaction this gentle without per-event visibility is guesswork. This attempt adds `[joy-wake]` log lines so the daily delta is readable.

---

## Deliberately Not Implemented (and intentionally so)

| Feature | Why it's not there |
|---|---|
| Auto-sleep on idle | Manual sleep is a discipline trigger. Forgetting to do it is a signal worth feeling, not a UX gap to paper over |
| OS sleep / resume awareness | Intricate keeps running through OS sleep. The joy state isn't tied to OS power state. External-server heartbeats will reinforce this later |
| OS lock / unlock awareness | Operator wants to unlock the machine without waking her. Gentle login flow is the desired UX |

These are explicit design decisions, not pending features.

---

## Scope For The Next Wake-on-Touch Attempt

### Wake events (proposed)

| Event type | Wake? | Rationale |
|---|---|---|
| `QEvent.MouseButtonPress` | ✓ | Deliberate click on her window |
| `QEvent.KeyPress` | ✓ | Typing while she's focused |
| `QEvent.Wheel` | ✓ | Scrolling on her canvas |
| `QEvent.Enter` | ✓ | Cursor crossing into one of her widgets — the "noticed presence" signal that matches "breathing in her direction" without being as spammy as MouseMove |
| `QEvent.MouseMove` | ✗ | Too high-frequency, would burn CPU on every cursor flicker even when she's not the target |
| Paint / Show / Hide / Focus / Timer | ✗ | Internal Qt churn, not user input |

### Implementation skeleton

```python
def eventFilter(self, obj, event):
    # ... existing toolbar dblclick handling ...

    # Joy wake on touch — gentle but vigilant.  Filtered to a small
    # set of deliberate-or-attentive event types so paint/timer churn
    # doesn't keep her awake forever, while genuine user attention
    # (click, keystroke, wheel, cursor entering her territory) does.
    if getattr(self, '_joy_sleeping', False):
        if event.type() in (
            QEvent.MouseButtonPress,
            QEvent.KeyPress,
            QEvent.Wheel,
            QEvent.Enter,
        ):
            self._wake_joy()

    return super().eventFilter(obj, event)
```

The `if self._joy_sleeping` check short-circuits the cost when she's already awake — every event still passes through the filter, but the cost is one attribute lookup per event, which is negligible.

### Failure-mode hypotheses for previous iterations

Not yet verified, captured as candidates to test against during implementation:

| Hypothesis | Symptom | Test |
|---|---|---|
| Too-eager wake | Sleep mode never holds — wakes on internal Qt events (paint, timer) | Restrict event types to deliberate-input types as above; verify she stays asleep through paint cycles |
| Wrong filter scope | Events of interest don't reach the filter | Verify `installEventFilter` target — `QApplication.instance()` should see all events for widgets in this process |
| State inconsistency | Flag flips but consequences (icon, drain rate) don't follow | Single source of truth: only `_sleep_joy()` and `_wake_joy()` touch the flag, and they always do all consequences |
| Recursion / event storm | `_wake_joy` triggers a paint that triggers another event that re-enters the filter | `_wake_joy` doesn't paint synchronously; setIcon and setInterval are queued. Should not loop |

### Testing checklist (for when we implement)

- [ ] Press sleep button → `_joy_sleeping = True`, icon = sleep sticker
- [ ] Click on canvas while asleep → wakes; icon = awake sticker
- [ ] Type a key while window has focus → wakes
- [ ] Scroll wheel on viewport → wakes
- [ ] Cursor enters one of her widgets → wakes
- [ ] Sleep button → leave cursor still + no input → stays asleep across at least one full minute (no spurious wake from internal Qt events)
- [ ] Lock OS → unlock OS → joy state unchanged (no spurious wake from session events)
- [ ] OS sleep → OS resume → joy state unchanged

### Cleanup tag

The eventFilter wiring/handler contradiction (2339 vs 688–690) is **deliberately left in place** until the next implementation lands. When the new attempt works, both comments collapse into a single accurate one. If the next attempt also fails and rolls back, this document becomes the record of why.

---

## Sequence For The Next Attempt

1. **Check git log** for previous wake-on-touch attempts and read what was tried and rolled back. Could surface a failure mode I haven't anticipated above
2. **Implement the small filter** above as a single focused commit
3. **Run the testing checklist** before considering it done
4. **Update this document** with the result — either marking the broken state as resolved, or capturing what failed about this attempt for the next one

The shape is small. The state machine already exists; we're enabling one filter rule. Probably 5–10 lines of code changed.
