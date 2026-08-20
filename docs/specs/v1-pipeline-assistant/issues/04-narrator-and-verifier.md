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

**Status:** ready-for-human

- [x] Prose is generated from the facts alone and leads with the answer in two or
      three sentences
- [x] The narrator never receives the table, the source rows, or the flags
- [x] A successful verification publishes the prose with a badge naming the
      verified figure count
- [x] Prose containing a figure absent from the facts is discarded entirely and
      the template publishes with a blocked badge
- [x] Prose writing a thousands shorthand of a currency fact is blocked
- [x] Percent, count, and date facts do not generate thousand or million variants
- [x] Period year, day of quarter, and days in quarter verify as facts rather
      than as pattern exemptions
- [x] A narrator API failure or timeout publishes the template through the same
      fallback path as a verification failure
- [x] No numeric token is exempted from checking by regex pattern

**Implementation notes:** `acme/narrator.py` adds `narrate()`, the single
entry point mirroring `router.route()`'s shape: it takes the question, the
restatement, the facts, the template, and the client, and always returns a
`Narration` (`prose`, `source`, `verified_figures`, `blocked`). Its signature
is the structural guarantee behind "the narrator never receives the table,
the source rows, or the flags" — it has no parameter to accept them.
`_call_model` calls `client.messages.create` with the system prompt (use
only the supplied figures, write them in full, never round/recompute/invent,
two or three sentences, lead with the answer, no hedging, no "check a
dashboard") and returns `None` on any exception, timeout included.

`acme/verifier.py` adds `verify()`. Numeric tokens are pulled with a
regex requiring a word boundary before the first digit, which is what keeps
"2026" out of "Q2-2026" from being misread as a stray "2" while still
catching the real "2026". The allowed set is every fact's value plus
rounding-only variants: all facts round to the nearest whole number
(absorbs float-sum noise, e.g. a `closed_won` sum landing on
517999.9999997), and percent/count/date facts additionally round to one and
two decimals. Currency facts get no variant beyond the whole-number
rounding — deliberately never a division by a thousand or a million, since
adding that would make "1,991" verify against a 1,991,000 fact, which is
the exact shorthand this module exists to block. Interpreting the parent
spec's "division... applies to currency facts only" as permission to add
such a variant would contradict its own acceptance criterion, so it's read
here as scoping a risk that's unique to currency, not as a variant that gets
generated.

`Answered` gained `narrator_blocked: bool`, false by default, distinguishing
"the template is on screen because narration was never attempted" (no
client — unchanged pre-issue-04 behavior) from "narration was attempted and
blocked" (API failure/timeout or a verification miss — both set it true,
matching "one fallback path, two triggers"). `pipeline.py`'s `ask()` calls
`narrate()` unconditionally once a result exists, passing the same `client`
already used for routing, matching "the model is used exactly twice."
`app.py` renders the verified-count caption when `prose_source == "narrator"`
and a "model output blocked" caption when `narrator_blocked` is true.

Verified live against the real API (`anthropic.Anthropic()`, no stub): of
four consecutive live narrations for the same Q2 headline question, three
verified in full (8-9 figures each) and one was correctly blocked when the
model summed `win_rate_weighted` and `closed_won` into an uncomputed total
of 5,323,522 — proof the block fires on genuine model arithmetic, not just
on stubbed adversarial input. 8 tests in `tests/test_narrator_and_verifier.py`
using a stub client that answers both the router's tool-use call and the
narrator's text call (distinguished by whether `tools` is in the request
kwargs), 50 passing overall.
