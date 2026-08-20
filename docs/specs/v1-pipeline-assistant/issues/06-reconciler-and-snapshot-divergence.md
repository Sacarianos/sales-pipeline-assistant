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

**Status:** ready-for-agent

- [ ] The change log carries one row per deal per changed field with both
      snapshot values
- [ ] All six change types are produced
- [ ] ID reuse is detected by account name and created date both changing, with
      no hardcoded deal IDs anywhere in the system
- [ ] Thirteen IDs classify as reused
- [ ] Twelve of those would otherwise classify as unwon and do not
- [ ] Four deals classify as genuine unwins, worth 363,000
- [ ] Reused IDs account for 1,220,000
- [ ] Four deals classify as new in Q2, one as reopened, and one carries a value
      drift outside the reused set
- [ ] Asking about Q1 closed-won leads with 6,041,000 at 102.0 percent and shows
      4,050,000 at 68.4 percent restated
- [ ] The divergence flag decomposes the 1,991,000 gap into unwins and reused IDs
      with separate counts and values
- [ ] Deals in the source rows that changed between snapshots raise the
      changed-deals flag
- [ ] No answer compares a stage across snapshots
