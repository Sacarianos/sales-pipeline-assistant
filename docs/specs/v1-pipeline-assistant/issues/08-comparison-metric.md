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

**Status:** ready-for-agent

- [ ] Asking how Q2 compares to the same point in Q1 returns 8.4 percent against
      21.3 percent
- [ ] The gap of roughly 13 points exists as its own precomputed fact
- [ ] Day 32 of Q2 resolves to May 2 and day 32 of Q1 to February 1
- [ ] The Q1 side is computed from the Q1 snapshot and the Q2 side from the Q2
      snapshot, with no blending
- [ ] The Q1 day-32 figure reads 1,260,000 across 10 deals at 21.3 percent
- [ ] The same-day-of-quarter definition appears as a flag
- [ ] The backloading flag reports how much of Q1's eventual total had landed by
      February 1
- [ ] A comparison intent without a comparison target is refused by validation
- [ ] Comparison answers at overall and segment groupings and refuses at rep and
      manager
