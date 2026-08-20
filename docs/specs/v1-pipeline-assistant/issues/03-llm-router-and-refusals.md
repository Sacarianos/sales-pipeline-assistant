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

**Status:** ready-for-human

- [x] Routing uses tool use with tool choice forced to the single query tool
- [x] The intent carries metric, grouping, period, comparison target, segment,
      rep, manager, restatement, and an optional unsupported reason
- [x] The router prompt is built from the catalog, descriptions and examples
      included
- [x] No data row reaches the router prompt
- [x] Asking about the West region refuses, naming both region definitions and
      reporting 17 of 92 deals in disagreement, computed at load time
- [x] Asking about Slack sentiment refuses with the coverage list read from the
      catalog
- [x] A question naming no quarter resolves to the quarter containing the as-of
      date, and the restatement names the assumed quarter
- [x] A question needing an unknown metric, segment, or rep refuses instead of
      substituting a near match
- [x] With the model API unreachable, the answer still renders, carries a
      distinct degraded banner, and shows a populated restatement
- [x] The offline router can return unsupported rather than guess

**Implementation notes:** `acme/router.py` gains `route_online`, which
calls `client.messages.create` with `tool_choice` forced to a single
`route_question` tool whose `input_schema` is `Intent.model_json_schema()`
patched with enums read off the catalog (metric names plus `unsupported`,
groupings, periods, segments, reps, managers). The system prompt is built
the same way, from metric descriptions and examples, the catalog's segments,
reps, managers, and periods, and the as-of date — never a data row. `route()`
tries the online path when a client is given and falls back to the existing
offline keyword router (`route_offline`, unchanged from issue 01) on any
exception, so a missing key, a network failure, or a malformed tool call all
degrade the same way.

Region is handled as a deterministic pre-check in `route()`, ahead of both
routers: `Intent` has no field for a region filter, so the only way a model
could act on a region question is by substituting the nearest segment or rep
— a substitution `validate()` cannot catch, since the substituted value would
be a real one. `_mentions_region` matches on "region" or any region name;
`Catalog.region_refusal_reason()` reports the mismatch count between each
deal's own region and its rep's home region, computed once at load time in
`acme/loading.py` (`Data.region_mismatch_count` / `region_deal_count`,
17 of 92 in this dataset) and carried onto the `Catalog`. The out-of-scope
(Slack) refusal was already catalog-driven from issue 01 and needed no
change.

`app.py` now constructs an `anthropic.Anthropic()` client once, guarded by
try/except so a missing API key yields `client = None` rather than crashing
at startup, and passes it into `ask()`. A small dependency-free `.env` loader
was added to `acme/config.py` (`os.environ.setdefault`, no
`python-dotenv`) so a local `ANTHROPIC_API_KEY` is picked up without a new
package. The offline banner moved from a caption to `st.warning`, shown for
both answered and refused turns whenever `router_mode == "offline"`, and the
refused branch now surfaces `intent.restated` inline rather than only in the
trace panel — needed once a refusal itself can be routed offline. Verified
live against the real API once a key was added: five questions covering
attainment overall, by rep, by segment, an out-of-scope metric, and region
all routed online with correctly filled intents; the region question's
`restated` and `unsupported_reason` came back byte-identical to the
deterministic pre-check text, confirming the model is never actually called
for it. Also verified in-browser, including the offline-fallback banner and
template answer against an unreachable client. 11 tests in
`tests/test_llm_router_and_refusals.py`, using a duck-typed stub client
matching `anthropic.Anthropic`'s `messages.create` shape (per the parent
spec's testing decisions, `route()` itself is not a direct seam — every test
goes through `ask()`), 38 passing overall.
