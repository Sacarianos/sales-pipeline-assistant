# 02: Fallback lane

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**Reworked under ADR-0007.** The lane now asks for a structured query plan
instead of a pandas expression, and the sandbox this issue ran expressions
through is gone. Lane precedence, the frames, flags, narration, and the badge
are unchanged. A decline or a rejected plan now says why on the refusal, and
the region columns are withheld from every plan. The notes below describe the
lane as first built.

**What to build:** The lane itself. A question the registry doesn't cover
reaches a generator, comes back as a pandas expression, runs through the
sandbox, and returns an answer instead of a refusal.

Precedence is the whole design here. Refused topics short-circuit first,
before any model call, region being the only one. The router runs next and a
registered metric that validates always wins, because a metric encodes a
business definition a human agreed to and a generated expression does not.
Only then does the fallback attempt the question. If it declines or its
expression fails validation, the system refuses with the catalog coverage
hint the way V1 does.

Product line was briefly a second refused topic and is not one. Region
refuses because two definitions of it measurably disagree; product line had
nothing to disagree with, so the refusal rested on an assumption about
bundled deals rather than on the data. It is answered by the `product_mix`
metric now, which puts it in the metric lane and makes it a useful check on
precedence: a question a registered metric covers must reach that metric and
never the generator.

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
- [x] Product line is answered by the `product_mix` metric in the metric lane,
      never refused and never handed to the generator
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
refuses on its own, it only answers or steps aside. Refused topics were
generalized in `router.py` into one `RefusedTopic` shape (label, word
pattern, catalog values, a reason method) walked as a small registry in
`route()`. That generalization was written when there were two entries,
region and product line; product line has since been removed, and the shape
was kept anyway because what it captures is the mechanics of a pre-routing
refusal rather than any particular reason for one. Facts are derived generically from
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

15 tests in `tests/test_fallback_lane.py`. Reviewed via `/code-review` on
both axes; the sandbox mutual-exclusion gap (shared with issue 01), the
discarded `restated`, and the router duplication were all fixed in response.

Later, on merging main into this branch: main had reversed product line into
the `product_mix` metric, so the refused-topic entry, its catalog reason
method, and the load-time count it quoted were all removed here, and the two
tests asserting the refusal became one asserting product line answers in the
metric lane instead. 172 passing after the merge.
