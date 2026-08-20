# 07: Risk metric

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader asks which reps are at risk of missing Q2 and
gets a list they can act on this week, with the reps who are safe named just as
clearly as the ones who aren't.

Risk is best-case coverage. For each rep, closed-won plus open pipeline against
quota, with both sides filtered by period membership the same way every other
number in the system is. Anyone below 100 percent is flagged, which means they
cannot make quota even if every open deal they have closes.

A pace-based rule is explicitly rejected. At day 32 seven of ten reps have closed
nothing, so pace flags almost everyone and tells a leader nothing they can use.
The threshold used here is an invention, not a Acme standard, and the flag
panel says so in those terms so that nobody repeats it as company policy.

Risk answers at overall and rep groupings only. A segment-level or manager-level
risk figure would be a sum of rep best-cases against a summed quota, which hides
the individual shortfall that makes the metric worth having.

Facts carry the organization rollup plus one fact per rep who clears 100 percent,
keyed by rep and labelled with the rep's name, so the narrator can name them
without ever holding the full roster. Reps below 100 percent live in the table
and the source rows and are never named in prose. This scales with the
interesting case rather than with headcount, so a quarter where everybody clears
produces ten clear-facts and a quarter where nobody does produces none.

The shortfall against quota is precomputed as its own fact. The narrator is
forbidden from arithmetic, so a gap stated in prose can never be a subtraction it
performed between two other facts.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Asking which reps are at risk of missing Q2 returns eight of ten below 100
      percent best case
- [ ] Marcus Rivera reads 132.4 percent and James Okafor reads 124.7 percent
- [ ] Organization best case reads 5,716,000 against a 6,200,000 quota
- [ ] The 484,000 shortfall exists as its own precomputed fact
- [ ] Closed-won and open pipeline are both filtered by period membership
- [ ] Facts carry one entry per rep clearing 100 percent, labelled with the rep's
      name
- [ ] Reps below 100 percent appear in the table and source rows and are never
      named in prose
- [ ] The invented-rule flag states the threshold is ours rather than Acme's
- [ ] Risk answers at overall and rep groupings and refuses at segment and
      manager
- [ ] No pace-based calculation appears anywhere in the metric
