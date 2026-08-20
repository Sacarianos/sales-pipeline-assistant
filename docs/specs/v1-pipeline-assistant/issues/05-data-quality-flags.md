# 05: Data-quality flags

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader is told, without asking, when the data behind
an answer has a problem worth knowing about. Stale forecast dates, missing
values, and stage names the system doesn't recognize all surface in the flags
panel next to the answer they affect.

Each rule is a function taking a result, an intent, and context, returning a flag
or nothing. All rules run and all results are collected, because the list itself
is displayed rather than being buried as conditionals inside metric code.

Stale close date catches open deals whose forecast close has already passed as of
2026-05-02. Two deals in the Q2 snapshot qualify. A leader forecasting on
pipeline that was supposed to have closed already should know that before they
commit to a number.

Missing field catches nulls in a field the answer depends on. One of the nine
closed-lost deals has no loss reason.

Unknown stage is the loud half of the open-as-complement decision. An
unrecognized stage still counts as open, and the flag says the system met a name
it hadn't been told about. The alternative is a whitelist that silently shrinks a
number when the vocabulary changes, which is how a wrong figure reaches a screen
with nothing to warn anyone.

**Blocked by:** 01

**Status:** ready-for-human

- [x] Open deals with a close date at or before the as-of date raise the stale
      flag, naming the deals
- [x] Two deals qualify as stale in the Q2 snapshot
- [x] Nulls in a field the answer depends on raise the missing-field flag
- [x] The single closed-lost deal with no loss reason is caught by that rule
- [x] A stage name absent from the known-stage registry raises the unknown-stage
      flag and the deal still counts as open
- [x] Every rule runs on every answer and all resulting flags are collected, with
      no rule short-circuiting another
- [x] Flags render in the panel without any click

**Implementation notes:** `acme/flags.py` gains `stale_close_date` and
`missing_field`. `unknown_stage` was already in place (added ahead of this
ticket) and needed no change beyond the module docstring. Both new rules
read `data.deals(result.snapshot)` — the whole snapshot that answered the
question — rather than `result.source_rows`, for the same reason
`unknown_stage` reads off `data`: the two reference cases (the stale pair,
the loss-reason gap) don't survive period-membership filtering. The missing
loss-reason deal, OPP-008, carries a Q1-dated `close_date` inside the *Q2*
snapshot (one of the deals whose close date crossed the quarter boundary,
per the parent spec's reconciliation section), so a Q2-period-filtered
`result.source_rows` never contains it; reading the raw snapshot instead
surfaces it on any question the Q2 snapshot answers, regardless of segment,
rep, or manager scope — a data-quality caveat about the pipeline, not about
the one slice asked for. The two stale deals (OPP-066, OPP-075) do carry a
Q2 period and would have matched via `source_rows` too, but scoping both
rules the same way keeps one story instead of two.

`acme/metrics/attainment.py`'s `SOURCE_COLUMNS` gained `loss_reason` so
it's visible in the source-rows table, though the flag rule no longer
depends on it being there. Verified with the real Q2 snapshot: stale names
OPP-066 (Oakwood Fitness) and OPP-075 (Brightside Media), missing-field
names OPP-008 (Ironbridge) — both match the parent spec's reference counts
(two stale, one of nine missing a reason). Unknown stage has no naturally
occurring case in the shipped CSVs, so its test loads a small synthetic
snapshot through the real `load_data()` rather than reaching into the rule
directly, keeping the primary seam (`ask()`) as the entry point either way.
4 tests in `tests/test_data_quality_flags.py`, 50 passing overall (shared
count with issue 04, implemented together).
