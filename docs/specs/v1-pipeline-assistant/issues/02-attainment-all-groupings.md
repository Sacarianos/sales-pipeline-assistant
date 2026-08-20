# 02: Attainment across every grouping, with filter-agreement validation

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader can ask about attainment for the whole
organization, one segment, one rep, or one manager, and gets the same quality of
answer in every case. Asking a question whose filters contradict each other gets
a refusal naming the two filters that conflict, rather than a confident answer to
a question nobody asked.

This is the first ticket that delivers a headline acceptance case. Enterprise
this quarter reads 165,000 closed against a 3,650,000 quota at 4.5 percent, with
3,600,000 sitting open.

Open pipeline is excluded from the attainment number itself. Best-case and
win-rate-weighted figures are computed as separate named facts and never folded
into attainment, because folding them in is exactly the kind of silent
redefinition that costs trust.

Filter agreement is one generalized rule over any pair among rep, segment, and
manager, resolved through the rep-to-segment and rep-to-manager lookup in the
quota source. Manager is a strict function of segment in this data, so a manager
paired with the wrong segment is as nonsensical as a rep paired with the wrong
segment, and silently dropping one of the two filters would answer a different
question than the one asked.

The small-sample rule belongs here, since grouping down to a single rep is the
first thing that produces a headline number resting on very few deals.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Enterprise this quarter returns 165,000 closed, a 3,650,000 quota, 4.5
      percent, and 3,600,000 open
- [ ] Attainment answers at overall, segment, rep, and manager groupings
- [ ] Open pipeline is excluded from the attainment figure and present as its own
      named fact
- [ ] Best-case and win-rate-weighted figures exist as separate named facts
- [ ] A rep paired with a segment they don't belong to returns a refusal naming
      both filters
- [ ] A manager paired with a conflicting segment returns the same shape of
      refusal
- [ ] A manager paired with a rep they don't manage returns the same shape of
      refusal
- [ ] Filter agreement is one rule covering all three pairs, not three
      near-duplicate checks
- [ ] A headline number resting on fewer than five deals raises the small-sample
      flag
