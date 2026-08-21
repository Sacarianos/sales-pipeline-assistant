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

**Status:** ready-for-agent

- [ ] A valid expression over an allowlisted frame returns a result
- [ ] `__class__`, `__globals__`, and any other underscore attribute are
      rejected by one rule rather than by enumeration
- [ ] Imports, lambdas, comprehensions, assignments, and walrus are rejected
- [ ] A call to a method not on the allowlist is rejected
- [ ] A reference to a name that isn't an allowlisted frame is rejected
- [ ] Reaching a builtin fails even if validation were bypassed
- [ ] Validation runs before execution and a rejected expression never executes
- [ ] A rejected expression refuses rather than being repaired or retried
- [ ] The result is a DataFrame, a Series, or a scalar, and anything else
      refuses
- [ ] A result larger than the row cap is truncated for display with the full
      count reported
