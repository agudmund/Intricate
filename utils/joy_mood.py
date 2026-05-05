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
# STATE
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class JoyMood:
    """Tri-state mood model with intensity-modulated decay and permanence.

    Instantiate once per running app.  Call ``tick(bar_value, dt)``
    every second (or whatever cadence the joy timer runs at).  Read
    ``state`` to drive UI / audio / chrome differentiation.
    """

    happy_secs:         float = 0.0
    last_session_secs:  float = 0.0
    permanence:         bool  = field(default=PERMANENCE_DEFAULT)

    # Internal — tracks current 100% session duration.  Reset to 0
    # each time the bar leaves 100%; rolls into last_session_secs.
    _current_session_secs: float = 0.0

    def tick(self, bar_value: int, dt_secs: float) -> None:
        """Advance the model by ``dt_secs`` of wall-clock time.

        ``bar_value`` is the joy bar percentage 0–100.  Caller is
        responsible for invoking once per timer tick with the current
        bar value.
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

    @property
    def state(self) -> str:
        """Current tri-state mood label.

        See module docstring for the semantics.  Caller renders
        differently per state — JoyStats label, chrome pulse hue,
        meow tier, etc.
        """
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
