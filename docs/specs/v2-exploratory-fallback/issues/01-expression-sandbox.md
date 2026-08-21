# 01: Expression sandbox

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** The safety boundary the whole lane rests on. A function that
takes a pandas expression as a string and either returns a validated, executed
result or refuses, with nothing in between.

Validation is an AST walk, not a regex and not a blocklist. The expression is
parsed with `ast.parse(mode="eval")` and every node is checked against an
allowlist of node types, frame names, and method names. Anything not on the
list is rejected. A blocklist would have to anticipate every escape; an
allowlist only has to be small.

Attribute access to any name beginning with an underscore is rejected in one
rule, which closes `__class__`, `__globals__`, `__subclasses__`, and the rest
of that family without enumerating them.

Execution binds only the allowlisted frames and an emptied `__builtins__`, so a
name the allowlist somehow let through still resolves to nothing.

Validation runs before execution, always. A rejected expression refuses. It is
never repaired, never partially executed, and never retried with the offending
clause removed, because a repaired query answers a question nobody asked.

This is the highest-risk code in the system, so it is a direct test seam rather
than something inferred through the pipeline, and its tests are adversarial
rather than illustrative.

**Blocked by:** none

**Status:** ready-for-human

- [x] A valid expression over an allowlisted frame returns a result
- [x] `__class__`, `__globals__`, and any other underscore attribute are
      rejected by one rule rather than by enumeration
- [x] Imports, lambdas, comprehensions, assignments, and walrus are rejected
- [x] A call to a method not on the allowlist is rejected
- [x] A reference to a name that isn't an allowlisted frame is rejected
- [x] Reaching a builtin fails even if validation were bypassed
- [x] Validation runs before execution and a rejected expression never executes
- [x] A rejected expression refuses rather than being repaired or retried
- [x] The result is a DataFrame, a Series, or a scalar, and anything else
      refuses
- [x] A result larger than the row cap is truncated for display with the full
      count reported

**Implementation notes:** `acme/sandbox.py`'s `_validate_node` is an
explicit-dispatch recursive walker (one `isinstance` branch per allowed AST
node type, an `else: raise Rejected(...)` catching everything else) rather
than an allowlist-of-types check, so a node type nobody wrote a branch for
rejects by construction instead of by remembering to add it to a set.
`validate` always runs before `execute`; `run` composes the two and never
calls `execute` on a tree `validate` rejected. `execute` independently binds
only the given frames with `__builtins__` emptied, so even a hand-built tree
that skips `validate` entirely (`test_reaching_a_builtin_fails_even_if_validation_were_bypassed`)
finds nothing reachable.

One gap surfaced during code review and is fixed here rather than filed
separately, since it's this issue's own guarantee: the per-node walker
validated each `Name` against the frame allowlist individually but had no
whole-expression check, so `deals_q1['deal_value'].sum() + deals_q2['deal_value'].sum()`
validated and executed, silently blending the two snapshots. Added
`mutually_exclusive`, a parameter on `validate`/`run` naming frame groups
that may never co-occur in one expression, checked once over the whole tree
after the per-node walk passes. `sandbox.py` itself stays generic — it has
no idea what "deals_q1" means — the fallback lane's call site is what says
these two may never appear together (issue 02's notes cover that side).
Two adversarial tests added for it.

29 tests in `tests/test_expression_sandbox.py`. Reviewed via `/code-review`
on both axes; the mutual-exclusion gap was the standards/spec reviewers'
most-severe finding on either axis and is fixed above.
