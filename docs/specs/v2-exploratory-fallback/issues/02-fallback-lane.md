# 02: Fallback lane

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** The lane itself. A question the registry doesn't cover
reaches a generator, comes back as a pandas expression, runs through the
sandbox, and returns an answer instead of a refusal.

Precedence is the whole design here. Region short-circuits first, before any
model call, exactly as it does today. The router runs next and a registered
metric that validates always wins, because a metric encodes a business
definition a human agreed to and a generated expression does not. Only then
does the fallback attempt the question. If it declines or its expression fails
validation, the system refuses with the catalog coverage hint the way V1 does.

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

**Status:** ready-for-agent

- [ ] A product-line question answers in the fallback lane with a table
- [ ] A question a registered metric covers is answered by the metric lane,
      asserted by the lane marker
- [ ] Region refuses and no generation is attempted
- [ ] A question needing a column nobody has refuses rather than answering
- [ ] The generator prompt contains no data row
- [ ] The lane exposes per-snapshot frames and no combined frame
- [ ] A generated expression failing validation returns a refusal with the
      catalog coverage hint
- [ ] Prose in the fallback lane is still verified against facts
- [ ] The generator uses `claude-sonnet-5` from the configuration constant
- [ ] The fallback degrades to a refusal when the model API is unreachable
