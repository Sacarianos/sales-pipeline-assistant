# 02: Fallback lane

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** The lane itself. A question the registry doesn't cover
reaches a generator, comes back as a pandas expression, runs through the
sandbox, and returns an answer instead of a refusal.

Precedence is the whole design here. Refused topics short-circuit first,
before any model call: region as it does today, and product line joining it.
The router runs next and a registered metric that validates always wins,
because a metric encodes a business definition a human agreed to and a
generated expression does not. Only then does the fallback attempt the
question. If it declines or its expression fails validation, the system
refuses with the catalog coverage hint the way V1 does.

Product line refuses on attribution rather than on data quality, and the
wording has to earn that distinction. The column is clean: no nulls in either
snapshot, an identical value set across both, and every cross-snapshot change
already classified as ID reuse. What is unsettled is that each deal records
exactly one product line, so a product-line total assigns that deal's whole
value to one product. The refusal computes its own count at load time, names
the attribution question, and says the number is withheld pending a decision.
A refusal implying bad data where the data is fine would be caught by the
first analyst who looked, and would cost more trust than the number was worth.

The generator sees column names, dtypes, and the distinct values of
low-cardinality columns, in the same shape the router prompt already uses. It
never receives a data row, so it cannot leak a figure it was never shown.

It names frames per snapshot: `deals_q1`, `deals_q2`, `quotas`, `reps`. There
is no combined frame and no way to ask for one, because a fallback that
silently blends the two snapshots reintroduces the exact error the reconciler
exists to prevent.

A question needing a column nobody has gets a decline with a reason rather than
an expression over the nearest-looking column. Declining is cheap and a
plausible substitution is the one failure the verifier cannot catch.

The result becomes Facts the same way a metric's does, so the narrator still
sees only computed values and the verifier still checks every numeric token
against them. `Answered` grows a lane marker rather than gaining a parallel
type.

**Blocked by:** 01

**Status:** ready-for-human

- [x] A loss-reason question answers in the fallback lane with a table
- [x] An account-level question answers in the fallback lane
- [x] A question a registered metric covers is answered by the metric lane,
      asserted by the lane marker
- [x] Region refuses and no generation is attempted
- [x] Product line refuses and no generation is attempted
- [x] The product-line refusal names attribution, not data quality, and quotes
      a count computed at load time
- [x] A question needing a column nobody has refuses rather than answering
- [x] The generator prompt contains no data row
- [x] The lane exposes per-snapshot frames and no combined frame
- [x] A generated expression failing validation returns a refusal with the
      catalog coverage hint
- [x] Prose in the fallback lane is still verified against facts
- [x] The generator uses `claude-sonnet-5` from the configuration constant
- [x] The fallback degrades to a refusal when the model API is unreachable

**Implementation notes:** `acme/fallback.py`'s `attempt()` returns `None`
for every reason the lane can't answer (no client, unreachable API, a
decline, a rejected expression), which is the one thing `pipeline.py` checks
before falling through to the ordinary catalog refusal — the lane never
refuses on its own, it only answers or steps aside. Region and product line
were generalized in `router.py` into one `RefusedTopic` shape (label, word
pattern, catalog values, a reason method) walked as a small registry in
`route()`, replacing what would otherwise have been two structurally
identical `_mentions_*`/`*_intent` pairs — caught in code review as real
duplication, not a style nit, since `_match_value` already generalizes this
exact shape elsewhere in the same file. Facts are derived generically from
whatever shape the sandboxed result takes: a row-count Fact always exists
for a tabular result regardless of size, and per-row Facts join it only up
to `FACT_ROW_CAP` (8) rows, so a large result can still be narrated by its
count without ever letting the narrator cite a row nobody vetted — verified
live against the real API, where a 46-row result initially produced an
empty facts dict and the narrator wrote an apologetic non-answer that
trivially passed verification (zero numeric tokens); the row-count fact
fixes that. `Answered` gained `lane`, `expression`, and a `restated` field
promoted from a property that only ever read `intent.restated` — the
fallback lane has no `Intent`, so that property silently returned `""` for
every exploratory answer until code review caught it; both lanes now set
`restated` directly.

Two live-API findings worth carrying forward rather than re-discovering:
first, the generator's initial system prompt let the model reach for
`pd.concat`/`.add(fill_value=...)` to answer "why are we losing deals" and
"which accounts have the most pipeline" across both quarters, which the
sandbox correctly rejected (see issue 01's notes on `mutually_exclusive`)
but cost real answers until the prompt was strengthened to say so
explicitly and to default to `deals_q2` alone when no quarter is named.
Second, narration of a fallback answer is non-deterministic the same way a
metric answer's is — one run of "why are we losing deals" had the narrator
correctly cite six individual counts and verify; another run summed two of
them into "4 of 8" and got correctly blocked to the template. Neither is a
defect; both are the verifier working exactly as designed on a lane where
the interpretation, not just the arithmetic, is model-generated.

16 tests in `tests/test_fallback_lane.py`, 158 passing overall. Reviewed via
`/code-review` on both axes; the sandbox mutual-exclusion gap (shared with
issue 01), the discarded `restated`, and the router duplication were all
fixed in response.
