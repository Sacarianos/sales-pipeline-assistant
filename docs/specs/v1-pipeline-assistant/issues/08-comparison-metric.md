# 08: Comparison metric

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader asks how Q2 attainment compares to the same
point in Q1 and gets a comparison that is actually fair, with enough context that
they don't read a mid-quarter gap as a final result.

Comparison matches the same day of quarter rather than the same calendar date.
Day 32 of Q2 is May 2 and day 32 of Q1 is February 1. Comparing a third of one
quarter against the whole of another is the kind of quiet apples-to-oranges error
that survives a long time before anyone catches it.

Each side is drawn from the snapshot that owns it. The Q1 side comes from the Q1
snapshot and the Q2 side from the Q2 snapshot, and they are never blended. The
day-32 figure happens to be identical in both snapshots at 1,260,000, which makes
this comparison the one Q1 number that doesn't require the divergence discussion.

The gap between the two sides is precomputed as its own fact, since the narrator
cannot perform the subtraction.

The backloading flag is what stops a leader from projecting a 13-point mid-quarter
gap onto quarter end. Only 1,260,000 of Q1's eventual total had landed by
February 1, so Q1 finished strong from a slow start and Q2 being behind at the
same point means less than it appears to.

Comparison answers at overall and segment groupings in V1.

**Blocked by:** 06

**Status:** ready-for-human

- [x] Asking how Q2 compares to the same point in Q1 returns 8.4 percent against
      21.3 percent
- [x] The gap of roughly 13 points exists as its own precomputed fact
- [x] Day 32 of Q2 resolves to May 2 and day 32 of Q1 to February 1
- [x] The Q1 side is computed from the Q1 snapshot and the Q2 side from the Q2
      snapshot, with no blending
- [x] The Q1 day-32 figure reads 1,260,000 across 10 deals at 21.3 percent
- [x] The same-day-of-quarter definition appears as a flag
- [x] The backloading flag reports how much of Q1's eventual total had landed by
      February 1
- [x] A comparison intent without a comparison target is refused by validation
- [x] Comparison answers at overall and segment groupings and refuses at rep and
      manager

**Implementation notes:** `acme/metrics/comparison.py` reads the current
side exactly like `attainment` (no cutoff, since "now" already excludes
anything unclosed) and filters the comparison side to `close_date <=`
a cutoff computed by `periods.date_for_day_of_quarter`, a new helper that
maps a day count onto the comparison period's own calendar. `gap_pct` and
`comparison_eventual_closed_won` are precomputed facts, the latter feeding a
new `backloading` rule in `acme/flags.py` that also names the two
resolved calendar dates. Both new `validation.py` checks (target required,
target must be in the catalog) return refusals through the same path every
other validation failure does. The offline router gained
`_explicit_periods_in_order`/`_match_comparison_periods` so "Q2 versus Q1"
and "Q1 versus Q2" resolve to different (period, comparison_period) pairs
without a live model call; verified this doesn't break when the primary
period is the completed one (`day_of_quarter` already clamps to the full
quarter length, so no separate branch was needed once a code-review pass
pointed out the ternary in the metric was redundant with that clamping).
12 tests in `tests/test_comparison_metric.py`. Reviewed via `/code-review`
on both axes; two judgement-call findings (a redundant ternary and a
double period-match in the offline router) were fixed, nothing else raised.
