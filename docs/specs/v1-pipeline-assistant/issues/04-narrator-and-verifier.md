# 04: Narrator and verifier

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** The answer reads like a person wrote it, and carries a visible
badge saying how many of its figures were checked against computed values. When
any figure fails that check, the whole paragraph is thrown away and the
deterministic sentence takes its place, with a badge saying so.

This is the ticket that makes the trust argument demonstrable rather than
asserted.

The narrator receives the question, the restatement, and the facts. Nothing else.
Not the aggregate table, not the source rows, not the flags. It is told to use
only the supplied figures, write them in full with no shorthand, never round or
recompute or introduce a number not listed, keep to two or three sentences, lead
with the answer, avoid hedging, and never suggest checking a dashboard.

Verification pulls every numeric token out of the prose, strips currency symbols,
separators, and percent signs, and compares against an allowed set built from the
facts with honest variants, within a small tolerance.

Variant generation is scoped by unit. Division by a thousand and by a million
applies to currency facts only. Percent, count, and date facts get rounding
variants at whole, one decimal, and two decimals, and nothing more. Without that
scoping the verifier would quietly accept a four-digit shorthand for a
seven-digit currency figure, which is precisely the imprecision this system
exists to catch.

No numeric token is exempt by pattern. Values that appear in prose but aren't
metric outputs, such as the period year, the day of quarter, and the days in the
quarter, are supplied as facts rather than carved out of the check. One absolute
rule with no exceptions is a far easier thing to defend out loud than a rule with
a list of things it skips.

The template fallback covers an outright narrator failure or timeout as well as a
verification failure. One fallback path, two triggers. There is always something
correct on screen, so the worst case is a boring answer rather than an error.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Prose is generated from the facts alone and leads with the answer in two or
      three sentences
- [ ] The narrator never receives the table, the source rows, or the flags
- [ ] A successful verification publishes the prose with a badge naming the
      verified figure count
- [ ] Prose containing a figure absent from the facts is discarded entirely and
      the template publishes with a blocked badge
- [ ] Prose writing a thousands shorthand of a currency fact is blocked
- [ ] Percent, count, and date facts do not generate thousand or million variants
- [ ] Period year, day of quarter, and days in quarter verify as facts rather
      than as pattern exemptions
- [ ] A narrator API failure or timeout publishes the template through the same
      fallback path as a verification failure
- [ ] No numeric token is exempted from checking by regex pattern
