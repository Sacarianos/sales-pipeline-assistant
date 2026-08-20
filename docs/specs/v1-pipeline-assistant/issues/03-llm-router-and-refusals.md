# 03: LLM router, catalog-driven refusals, offline fallback banner

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader can phrase a question however they like and
have it understood, and gets an honest no when the system can't answer it
truthfully. This is where both negative acceptance cases land.

Routing is Anthropic tool use with one tool whose input schema is the JSON schema
of the intent model, enums populated from the catalog, and tool choice forced to
that tool. Free-form JSON in a text reply is not acceptable here.

The router receives column names and the distinct values of low-cardinality
columns. It never receives a data row, so it is structurally incapable of leaking
a number into the prompt. The no-hallucinated-numbers guarantee should not rest
on prompt wording where it can rest on what the model was never shown.

When a question needs a metric, segment, or rep outside the catalog, the router
marks it unsupported and explains why. It does not substitute something close.
When a question doesn't name a quarter, the period defaults to the quarter
containing the as-of date and the restatement says so explicitly, so a wrong
default is as visible as a wrong metric.

Refusals never guess at a nearest match and never retry with a loosened
constraint. The region refusal computes its own numbers at load time instead of
quoting a written string, and the out-of-scope refusal reads its coverage list
from the catalog so it reads as a design decision rather than an apology.

The offline keyword router already exists from ticket 01. This ticket makes the
degraded path visible, because a keyword router misroutes far more often than the
model does and a misroute is the one failure the verifier cannot catch. It is
allowed to return unsupported when keyword matching is ambiguous, since refusing
is cheap and a wrong route is expensive.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Routing uses tool use with tool choice forced to the single query tool
- [ ] The intent carries metric, grouping, period, comparison target, segment,
      rep, manager, restatement, and an optional unsupported reason
- [ ] The router prompt is built from the catalog, descriptions and examples
      included
- [ ] No data row reaches the router prompt
- [ ] Asking about the West region refuses, naming both region definitions and
      reporting 17 of 92 deals in disagreement, computed at load time
- [ ] Asking about Slack sentiment refuses with the coverage list read from the
      catalog
- [ ] A question naming no quarter resolves to the quarter containing the as-of
      date, and the restatement names the assumed quarter
- [ ] A question needing an unknown metric, segment, or rep refuses instead of
      substituting a near match
- [ ] With the model API unreachable, the answer still renders, carries a
      distinct degraded banner, and shows a populated restatement
- [ ] The offline router can return unsupported rather than guess
