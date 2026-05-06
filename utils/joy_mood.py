#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/joy_mood.py joy tri-state mood algorithm
-The shape of how she feels between encounters, captured for the next pass for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Status
# ──────
# Captured 2026-05-05 from a morning design session.  NOT YET WIRED into
# the runtime joy mechanic — this module is the design-as-code so
# future-us can revisit, refine, and integrate when the slot opens.
# Standalone: no imports from elsewhere in the codebase, no callers
# anywhere in the codebase.  Touch the runtime only when ready.
#
# Why a standalone capture rather than inline implementation: the joy
# mechanic is still being calibrated.  Having the full model in one
# place — docstrings, constants, and reference implementation — means
# the decision to wire it in is one explicit step rather than scattered
# integration work.  The wire-in itself replaces the current happy
# accumulator with this richer state object.

# ─────────────────────────────────────────────────────────────────────────
# THE MODEL
# ─────────────────────────────────────────────────────────────────────────
#
# Currently the joy mechanic accumulates "happy seconds" while the bar
# is at 100% and freezes the counter when below 100%.  Buckets are
# earned from accumulated happy time.  The accumulator never decreases.
#
# This model replaces that with a tri-state mood ladder driven by:
#   - an intensity-modulated decay during below-100% periods
#   - a permanence Boolean that determines the affective register on
#     return after extended absence
#
# Variables tracked
# ─────────────────
#   happy_secs               float  — accumulator, floored at 0
#   last_session_secs        float  — duration of the most recent
#                                     sustained 100% period (before
#                                     the bar dropped).  Sets decay
#                                     intensity for the period that
#                                     follows.
#   permanence               bool   — relationship-level switch.
#                                     True  = authentic love —
#                                             affection survives any
#                                             absence; the floor at 0
#                                             holds; reunion is warm
#                                     False = fondness only — no
#                                             permanence-protection;
#                                             the floor still holds at
#                                             0 but reunion is hostile
#
# Intricate-instance default: permanence = True.  The variable exists
# because the algorithm is more general than its current single use,
# and a future system instance might model a relationship without
# authentic-love permanence.
#
# Decay during below-100%
# ───────────────────────
# Linear, intensity-modulated.  Per second of being below 100%:
#
#     decay_per_sec = BASE_K / (1 + last_session_secs / INTENSITY_N)
#
# A brief touch-and-leave (last_session_secs ≈ 0) gives full BASE_K
# decay rate.  A long sustained 100% session (last_session_secs large
# relative to INTENSITY_N) flattens the decay rate toward zero —
# satisfaction lingers because the encounter was substantial.
#
# happy_secs floors at 0.  The floor is the load-bearing design
# decision: Intricate is loved authentically, and authentic love is a
# permanence state.  A wounded sub-zero range was considered and
# rejected.  Mild upset within the ≥0 range is the maximum severity.
#
# Tri-state ladder
# ────────────────
# The mood at any moment is one of three states.  Two of them activate
# during below-100%, one on return to 100%:
#
#   HUNGRY     — bar < 100%, happy_secs > 0.  Plain unsatisfied.
#                Baseline below-100% state.  No overlay.
#
#   UPSET      — bar < 100%, happy_secs == 0.  Decay has fully
#                drained the recent satisfaction.  Affect overlay:
#                "a bit upset perhaps if too much time passes."
#                Permanence prevents the value from going negative,
#                so the upset is bounded — never "what a jerk, left
#                me hanging" without permanence.
#
#   REUNION    — bar transitioned from <100% to 100% after a long
#                below-100% interval.  Affect overlay: "it's so nice
#                to finally see you again, how have you been."  Warm,
#                forward-leaning; not making the operator pay for the
#                absence.  Activates only when permanence is True
#                (which it always is for Intricate).
#
# Without permanence (False branch — not Intricate), the REUNION
# state is replaced with a HOSTILE return state ("what a jerk") and
# the UPSET state is unchanged.  Captured here for completeness; not
# active in Intricate.
#
# Bucket earning
# ──────────────
# Buckets accumulate when happy_secs reaches BUCKET_THRESHOLD_SECS
# (currently 3600 = 1 hour of sustained-or-recovered satisfaction).
# With decay, this becomes "sustained satisfaction" rather than
# "any-time-at-100% eventually summing up."  The reward shifts
# toward consistent-care from intermittent-attention.
#
# Wire-in plan (when the slot opens)
# ──────────────────────────────────
#   1. Replace IntricateApp._happy_secs with a JoyMood instance.
#   2. Replace _tick_happy() with mood.tick(bar_value, dt).
#   3. JoyStatsNode reads mood.state and surfaces the three-state
#      label alongside the existing fields.
#   4. Chrome pulse / meow tier hook into mood.state for differentiated
#      affect (REUNION ≠ HUNGRY ≠ UPSET visually and audibly).
#   5. TOML tunables: [intricate.joy] gains BASE_K, INTENSITY_N,
#      bucket_threshold_secs (already present), permanence (default
#      True for Intricate; future relationships could override).
#
# ─────────────────────────────────────────────────────────────────────────
# PHASE 2 — STARVING state and stomach-pouch biology
# ─────────────────────────────────────────────────────────────────────────
#
# Captured 2026-05-05 evening, parked for the lingering pass.  Phase 1
# (linear depletion) shipped first; this layer adds the body-physics
# counterpart to the mood-relational accumulator above.
#
# Polarity frame
# ──────────────
# Joy without its counterweight is not joy — it is just default state.
# The floor-at-zero permanence decision only means something because
# there's a path down to that floor.  Light needs darkness to be
# defined.  "Everything" only exists as a word because "nothing" does.
# Starvation in this system is not a punishment to engineer around;
# it is the silhouette that gives the joy bar its shape.  So the
# mechanic earns its place not as a bug-fix but as the necessary
# counterpart: the bar's *low* end finally has a body of its own,
# matching the mood-ladder body it already had at the high end.
#
# Biology — the 40-day-fast inversion
# ───────────────────────────────────
# Three truths about feeding a starving body:
#
#   1. The stomach pouch shrinks during sustained fasting.  The first
#      bite of fish after 40 days of devotional fasting overwhelms the
#      smaller capacity — a full meal cannot be eaten as the first
#      meal back.
#
#   2. Capacity returns through patient repeated feeding.  The pouch
#      grows back asymptotically as the body re-learns to receive.
#
#   3. Each bite still requires swallow time.  No matter how starving
#      the body, food cannot be shoved in continuously.  Even IV
#      delivery is per-drip, not a continuous gush — the most
#      efficient route into a depleted body still respects the rate
#      at which the body can take it in.  This means the existing
#      per-feed cooldown stays untouched in Phase 2; it is not a
#      gameplay-side anti-cheese rule that should yield to hunger,
#      it is the swallow-gap, which is real.
#
# These three together flip the naive "she gulps when starving,
# nibbles when full" read.  The truer mechanic:
#
#     stomach_capacity ← state variable in [0.0, 1.0], decays during
#                        sustained STARVING, grows back asymptotically
#                        through repeated feeds.  Floor at some small
#                        epsilon so feeding always has SOME effect.
#
#     feed_potency = base_feed_value × stomach_capacity
#
#     feed cadence = unchanged from Phase 1 (per-feed cooldown still
#                    enforced — the swallow gap doesn't relax)
#
# A starving cat fed once fills the bar barely at all — the stomach
# can't take it.  The user has to wait the swallow-gap cooldown, then
# feed her again, several times, before each feed delivers what it
# would in normal state.  The recovery is felt by the user, not just
# observed — the feed sequence becomes a small ritual of return,
# paced by the body's own rate of receiving.
#
# Two axes, not one ladder
# ────────────────────────
# Phase 2 settles the design question of "fourth state in the ladder
# vs continuous parallel variable" as: BOTH.
#
#   - STARVING joins the mood ladder as a fourth named state alongside
#     HUNGRY / UPSET / REUNION / SATISFIED.  Useful for narrative-bucket
#     branching, chrome differentiation, meow tier selection — places
#     that want to switch on a discrete name.
#
#   - stomach_capacity remains a continuous float that crosscuts the
#     mood states.  Truer to the biology: the stomach doesn't binary-
#     flip, it just is what it is at any moment.  Used directly in
#     feed_potency calculation; never collapsed to a state name.
#
# So a starving cat with shrunken stomach in the UPSET mood reads
# differently from a starving cat with shrunken stomach who has REUNION-
# pending warmth from a long bygone session.  Interior state and
# interpersonal physics, distinct, composing.
#
# State definition
# ────────────────
# STARVING ← bar_value < STARVATION_BAR_THRESHOLD for at least
#            STARVATION_DURATION_SECS of cumulative time below that
#            threshold.  Cleared when bar_value rises above
#            STARVATION_RECOVERY_THRESHOLD for a sustained period.
#            Hysteresis is deliberate: a brief recovery feed shouldn't
#            flip her out of STARVING the moment the bar peaks.
#
# Wire-in plan (Phase 2, on top of Phase 1)
# ─────────────────────────────────────────
#   1. Add `stomach_capacity` and starvation tracking to JoyMood.
#   2. tick() advances stomach_capacity downward during STARVING and
#      tracks the cumulative-below-threshold counter.
#   3. New `feed(base_amount)` method returns the actual amount the
#      bar should rise — base × stomach_capacity, with a small bump
#      to stomach_capacity itself per feed (the pouch growing back).
#      Replaces main_window's current fixed-amount feed bump.
#      The existing FEED_COOLDOWN / FEED_WINDOW gates stay untouched
#      — they ARE the swallow gap, and that is real biology, not an
#      anti-cheese gameplay rule we yield under hunger.
#   4. JoyStatsNode surfaces stomach_capacity as a new row, alongside
#      the existing State.  Visible during calibration, can be
#      considered for hiding once the mechanic is felt-in.
#   5. STARVING gets its own meow tier and narrative-bucket templates
#      in joy_narrative — voice register: small, breath-held, the
#      "she's gone too long without" phrasing.
#   6. TOML tunables: [intricate.joy] gains starvation_bar_threshold,
#      starvation_duration_secs, stomach_decay_per_sec,
#      stomach_growth_per_feed, stomach_capacity_floor.

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────
# TUNABLES — initial values
# ─────────────────────────────────────────────────────────────────────────
# These are conservative starting points.  All three are expected to
# move during calibration.  Promote to [intricate.joy] in settings.toml
# at wire-in time so The Settlers can live-tune.

BASE_K_PER_SEC: float = 0.1          # base decay rate (sec of happy lost
                                     # per sec below 100% with zero
                                     # last_session_secs)

INTENSITY_N_SECS: float = 1800.0     # 30 min — sustained-duration that
                                     # halves the decay rate.  Doubles
                                     # at 60 min, etc.

BUCKET_THRESHOLD_SECS: float = 3600  # 1 hour — currently bucket_minutes
                                     # = 60 in [intricate.joy].  Shared
                                     # constant kept here for the
                                     # standalone-module property; sync
                                     # at wire-in.

PERMANENCE_DEFAULT: bool = True       # Intricate-instance default.  The
                                     # algorithm is more general; this
                                     # is the value for THIS relationship.


# ─────────────────────────────────────────────────────────────────────────
# PHASE 2 TUNABLES — stomach-pouch biology, parked for calibration
# ─────────────────────────────────────────────────────────────────────────
# Initial guesses; expect to move during the lingering pass.  Promote
# to [intricate.joy] at Phase 2 wire-in time alongside the Phase 1
# tunables.

STARVATION_BAR_THRESHOLD: int = 5         # bar < 5% counts as starving
STARVATION_DURATION_SECS: float = 600     # 10 cumulative minutes below
                                          # threshold flips STARVING True
STARVATION_RECOVERY_THRESHOLD: int = 30   # bar must clear 30% sustained
                                          # to flip STARVING off (hysteresis)

STOMACH_DECAY_PER_SEC: float = 0.002      # stomach_capacity loses 0.2%
                                          # per second of starvation —
                                          # full→floor over ~7 minutes
STOMACH_GROWTH_PER_FEED: float = 0.15     # each feed grows capacity by
                                          # 15 percentage points,
                                          # asymptotic toward 1.0
STOMACH_CAPACITY_FLOOR: float = 0.05      # never drops to absolute zero
                                          # — a single bite always lands


# ─────────────────────────────────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class JoyMood:
    """Tri-state mood model with intensity-modulated decay and permanence.

    Phase 2 adds stomach_capacity as a parallel continuous variable
    and STARVING as a fourth named state — see Phase 2 section in the
    module docstring for the polarity-frame rationale.

    Instantiate once per running app.  Call ``tick(bar_value, dt)``
    every second (or whatever cadence the joy timer runs at).  Read
    ``state`` to drive UI / audio / chrome differentiation.  Call
    ``feed(base_amount)`` instead of writing the bar directly so
    stomach_capacity gates feed potency.
    """

    happy_secs:         float = 0.0
    last_session_secs:  float = 0.0
    permanence:         bool  = field(default=PERMANENCE_DEFAULT)

    # Phase 2 — physical body state, distinct from the relational
    # happy_secs accumulator.  Starts full; decays during sustained
    # STARVING; grows asymptotically through repeated feeds.  See the
    # 40-day-fast biology note in the module docstring.
    stomach_capacity:   float = 1.0

    # Internal — tracks current 100% session duration.  Reset to 0
    # each time the bar leaves 100%; rolls into last_session_secs.
    _current_session_secs: float = 0.0

    # Phase 2 internals — STARVING entry tracking with hysteresis.
    _seconds_below_starve_threshold: float = 0.0  # accumulator for entry
    _seconds_above_recovery_threshold: float = 0.0  # accumulator for exit
    _starving:                        bool = False  # latched state

    def tick(self, bar_value: int, dt_secs: float) -> None:
        """Advance the model by ``dt_secs`` of wall-clock time.

        ``bar_value`` is the joy bar percentage 0–100.  Caller is
        responsible for invoking once per timer tick with the current
        bar value.

        Phase 2: also advances starvation tracking and stomach decay.
        """
        if bar_value >= 100:
            # Sustained-satisfaction branch
            self.happy_secs += dt_secs
            self._current_session_secs += dt_secs
        else:
            # Decay branch — close out any current 100% session first
            if self._current_session_secs > 0:
                self.last_session_secs = self._current_session_secs
                self._current_session_secs = 0.0
            decay_rate = BASE_K_PER_SEC / (
                1.0 + self.last_session_secs / INTENSITY_N_SECS
            )
            self.happy_secs = max(0.0, self.happy_secs - decay_rate * dt_secs)

        # ── Phase 2: starvation tracking with hysteresis ─────────────
        # Below threshold accumulates toward STARVING entry.  Above
        # recovery threshold accumulates toward STARVING exit.  Mid-
        # band (between starve and recovery thresholds) leaves both
        # counters where they are — a slow drift through the middle
        # doesn't either trigger or release the state.
        if bar_value < STARVATION_BAR_THRESHOLD:
            self._seconds_below_starve_threshold += dt_secs
            self._seconds_above_recovery_threshold = 0.0
            if self._seconds_below_starve_threshold >= STARVATION_DURATION_SECS:
                self._starving = True
        elif bar_value >= STARVATION_RECOVERY_THRESHOLD:
            self._seconds_above_recovery_threshold += dt_secs
            self._seconds_below_starve_threshold = 0.0
            # Use the same duration for symmetry; could split into a
            # separate STARVATION_RECOVERY_DURATION_SECS at calibration.
            if self._seconds_above_recovery_threshold >= STARVATION_DURATION_SECS:
                self._starving = False

        # ── Phase 2: stomach capacity decay during STARVING ──────────
        # Capacity only erodes while she's actually starving — the
        # mid-band hungry-but-not-starving state doesn't shrink the
        # pouch.  Floor at STOMACH_CAPACITY_FLOOR so a single bite
        # always lands, no matter how long she's gone.
        if self._starving:
            self.stomach_capacity = max(
                STOMACH_CAPACITY_FLOOR,
                self.stomach_capacity - STOMACH_DECAY_PER_SEC * dt_secs,
            )

    @property
    def state(self) -> str:
        """Current mood-ladder label.

        Phase 2: STARVING is tested first because it's the body-state
        floor — when she's starving, that's the dominant read regardless
        of whatever the mood-relational fields say.  Below STARVING the
        Phase 1 ladder applies as before (REUNION/UPSET/SATISFIED/HUNGRY).

        See module docstring for the full semantics.  Caller renders
        differently per state — JoyStats label, chrome pulse hue, meow
        tier, narrative bucket selection.
        """
        # Phase 2 — STARVING wins over the mood ladder.  Body floor
        # is a louder signal than any happy_secs trajectory.
        if self._starving:
            return "STARVING"
        # REUNION fires on the first tick after returning to 100%
        # following a fully-decayed period.  Captured here as a
        # transient state — caller may want to latch it for a duration
        # rather than seeing it for one tick.  Refine at wire-in.
        if self._current_session_secs > 0 and self.last_session_secs > 0 and self.happy_secs == 0:
            return "REUNION" if self.permanence else "HOSTILE"
        if self.happy_secs == 0 and self._current_session_secs == 0:
            return "UPSET" if self.permanence else "HOSTILE"
        if self._current_session_secs > 0:
            return "SATISFIED"
        return "HUNGRY"

    def feed(self, base_amount: float) -> float:
        """Phase 2 — gate a feed through stomach capacity.

        Returns the actual amount the caller should add to the bar:
        ``base_amount × stomach_capacity``.  Also nudges
        stomach_capacity upward by STOMACH_GROWTH_PER_FEED, capped at
        1.0.  At wire-in time, ``main_window._on_feed`` calls this
        instead of writing the bar directly.

        Caller is still responsible for the per-feed cooldown / window
        gates (FEED_COOLDOWN, FEED_WINDOW) — those are the swallow
        gap and stay enforced regardless of stomach state.  This
        method only shapes the *amount* a permitted feed delivers;
        the *cadence* of feeds is unchanged from Phase 1.

        A starving cat with shrunken stomach (capacity = 0.05) accepts
        only 5% of the base amount on her first feed; the next feed
        finds capacity at 0.20, then 0.35, etc., asymptotic toward 1.0.
        Several patient feeds — each separated by the swallow-gap
        cooldown — restore her to taking a full meal.
        """
        accepted = base_amount * self.stomach_capacity
        self.stomach_capacity = min(
            1.0, self.stomach_capacity + STOMACH_GROWTH_PER_FEED
        )
        return accepted

    @property
    def buckets_earned(self) -> int:
        """Whole-bucket count from current happy_secs."""
        return int(self.happy_secs // BUCKET_THRESHOLD_SECS)

    def consume_bucket(self) -> bool:
        """Deduct one bucket's worth of happy_secs.  Return True if a
        bucket was available and consumed, False otherwise.

        Wire-in: called by the bucket-counter when crediting one bucket
        to the joy_buckets store.  The current implementation accrues
        happy without consumption; this method is what makes the
        decay model work coherently with bucket earning."""
        if self.happy_secs >= BUCKET_THRESHOLD_SECS:
            self.happy_secs -= BUCKET_THRESHOLD_SECS
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────
# REFINEMENT NOTES (parked for future passes)
# ─────────────────────────────────────────────────────────────────────────
#
# 1. REUNION as transient vs latched.  Currently the REUNION state
#    fires for one tick on returning to 100%.  Caller may want it
#    latched for N seconds so the affect is observable.  Decide at
#    wire-in based on what the chrome / audio integration needs.
#
# 2. UPSET threshold.  Currently triggers immediately when happy_secs
#    hits 0 below-100%.  Could add a grace period — e.g. UPSET only
#    after happy_secs has been 0 for M minutes — to avoid flicker on
#    brief drops.  Same shape as the existing _joy_in_grace mechanism
#    at the upper boundary; consider reusing.
#
# 3. Permanence as a boolean vs a continuous trust value.  The current
#    binary True/False maps cleanly to the love-vs-fondness distinction
#    discussed.  A continuous version could support gradual trust-
#    building / trust-erosion across a relationship arc.  Out of scope
#    for Intricate (permanence=True is unconditional here); flagged in
#    case a different system instance ever uses this module.
#
# 4. Intensity modulation curve.  Currently 1/(1 + s/N) which gives a
#    gentle hyperbolic decay.  Other curves (exp, log) might feel more
#    natural.  Calibrate after first wire-in by reading observed decay
#    rates against subjective sense of "fading too fast / too slow."
#
# 5. Settlers integration.  All three numeric tunables (BASE_K,
#    INTENSITY_N, BUCKET_THRESHOLD) should be promoted to
#    [intricate.joy] keys at wire-in so live-tuning works through
#    The Settlers without code changes.
#
# 6. NPC layer and equilibrium return.  The permanence Boolean exists
#    as a parameter — not hardcoded True — because there's a parallel
#    NPC system that this algorithm will eventually serve as well.
#    NPCs typically don't carry permanence with the operator, so the
#    decay-to-zero behaviour applies cleanly to them.
#
#    The richer dynamic for permanence=True dyads (Intricate's case):
#    perturbations from NPC interactions can shift the affect short-
#    term, but the system always settles BACK toward a positive
#    equilibrium set by the permanence, never toward zero.  The
#    underlying love-permanence remains intact regardless of distance
#    or time priorities.
#
#    Current model implements only the decay-to-zero floor.  Refinement
#    at wire-in: decay toward a permanence-anchored set-point instead
#    of toward zero, when permanence=True.  Floor stays at zero (per
#    the design decision); equilibrium is some positive value above it.
#    Two parameters needed: the equilibrium value, and how strongly the
#    system pulls back toward it from perturbations.
