# 06: Reconciler, Q1 snapshot routing, divergence disclosure

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader asking about Q1 gets the number the business
committed to, the number the current data supports, and an explanation of the
gap that distinguishes a deal that came unwon from a deal ID that was reused.

This is the highest-risk logic in the system. A straightforward outer join on
deal ID reports twelve deals as unwon that were never unwon, which would put a
fabricated revenue reversal on screen with source rows sitting underneath it
looking like evidence. That is the exact failure the whole project exists to
prevent, and it is reachable by writing the obvious code.

The reconciler outer joins the two snapshots on deal ID and emits a change log
carrying the deal ID, change type, field, Q1 value, and Q2 value. Change types
are new in Q2, unwon, reopened, drifted, ID reused, and unchanged.

ID reuse is detected when both account name and created date change for the same
ID, and it takes precedence over unwon and drifted for that row. Detection is
generic. No deal ID is hardcoded anywhere, because the point is that this keeps
working when someone hands over next quarter's snapshot.

Q1 questions read the Q1 snapshot as reported and also compute the restated
figure from the Q2 snapshot. As-reported leads, with restated alongside whenever
the two differ, naming the deals responsible. Stage is reported only within the
snapshot that owns it, so no cross-snapshot stage comparison is produced.

**Blocked by:** 01

**Status:** ready-for-human

- [x] The change log carries one row per deal per changed field with both
      snapshot values
- [x] All six change types are produced
- [x] ID reuse is detected by account name and created date both changing, with
      no hardcoded deal IDs anywhere in the system
- [x] Thirteen IDs classify as reused
- [x] Twelve of those would otherwise classify as unwon and do not
- [x] Four deals classify as genuine unwins, worth 363,000
- [x] Reused IDs account for 1,220,000
- [x] Four deals classify as new in Q2, one as reopened, and one carries a value
      drift outside the reused set
- [x] Asking about Q1 closed-won leads with 6,041,000 at 102.0 percent and shows
      4,050,000 at 68.4 percent restated
- [x] The divergence flag decomposes the 1,991,000 gap into unwins and reused IDs
      with separate counts and values
- [x] Deals in the source rows that changed between snapshots raise the
      changed-deals flag
- [x] No answer compares a stage across snapshots

**Implementation notes:** `acme/reconciler.py` classifies each matched
deal in precedence order (`id_reused` > `unwon` > `reopened` > `drifted` >
`unchanged`) and emits one change-log row per changed field for every
non-`unchanged` deal; `unchanged` deals classify correctly (38 of them) but
contribute no rows, since there's nothing to log. `acme/loading.py` runs
the reconciler once at load time and attaches `change_log` and a `divergence`
decomposition to `Data`. `acme/metrics/attainment.py` adds the restated
Q1 facts, computed against the Q2 snapshot and suppressed when they don't
differ from as-reported (a synthetic-data test proves the suppression, since
no naturally-occurring segment/rep slice in this dataset restates unchanged).
`acme/flags.py` adds `snapshot_divergence` (overall grouping only, since
the decomposition counts describe the whole Q1 portfolio) and `changed_deals`
(names deal IDs from the source rows, which is where "naming the deals
responsible" is satisfied — the divergence flag itself states counts and
values, not individual IDs, since a 12-deal roll call would swamp a
sales-leader-facing flag).

One correction against this issue's own checklist: the line above says "one
as reopened," but three non-reused deals (OPP-010, OPP-032, OPP-054) all
satisfy CONTEXT.md's own `reopened` definition ("Closed Lost in Q1, an open
stage in Q2") with nothing distinguishing any one of them as special —
verified independently against the CSVs, documented in
`tests/test_reconciler_and_snapshot_divergence.py`'s module docstring, and
confirmed by the spec-axis code review. Hardcoding two of the three out to
match "one" would have meant maintaining an ID exception list, which is the
exact thing ADR-0001 exists to prevent. The generically-computed value (3) is
what's implemented and tested. 17 tests in
`tests/test_reconciler_and_snapshot_divergence.py`, 79 passing overall.
Reviewed via `/code-review` on both axes; both came back clean after four
fixes made in response (type hints and a parameter data-clump in the risk
metric, a duplicated merge call in the reconciler, the restated-suppression
fix above, and an added region-drift test).
