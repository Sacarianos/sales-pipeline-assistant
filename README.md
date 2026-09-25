# Acme pipeline assistant

A Streamlit chat app for a sales leader who wants a plain-English answer
about pipeline and quota, with the figures, the source rows, and every
assumption laid out next to it.

The previous AI reporting tool at Acme invented a number in front of the
CCO, and it's unusable now regardless of how often it happens to be right.
This one is built so that failure mode can't recur: the language model
never produces a number. A question a defined metric covers makes two model
calls, and a question outside the catalog makes a third.

## The trust argument

A question a registered metric answers makes exactly two model calls, and
neither touches a data row on the way to producing a figure. A question
outside the catalog makes a third call, covered under the exploratory lane
below, and that one never sees a data row either.

**Call one, the router.** It reads the question and calls a single forced
tool whose schema is the structured `Intent` the rest of the system runs on:
metric, grouping, period, segment, rep, manager, comparison target. The
enums in that schema come from the catalog (the actual metric names, rep
names, segment names in the data), and the prompt carries only that catalog
metadata, never a deal row or a dollar figure. A model that has never been
shown a number can't leak one into its answer, so the guarantee here rests
on what the model was never given, not on prompt wording asking it to
behave.

Every number in the answer is computed after this call, by pandas, from the
loaded CSVs. The model is not in that loop at all.

**Call two, the narrator.** It receives the question, the one-sentence
restatement of how it was read, and a mapping of already-computed facts:
values, units, human labels. Nothing else reaches it, not the dataframe, not
the source rows, not the flags. Its instructions forbid introducing any
number that isn't in that mapping and forbid combining two supplied numbers
into a new one, since a subtraction the model performs is exactly as
unverifiable as a number it invents outright.

**The verifier sits between the narrator and the screen.** It pulls every
numeric token out of the model's prose by regex, strips currency symbols and
separators, and checks each one against the fact values (plus a small set of
honest rounding variants, scoped so a currency fact can't be shortened to
thousands and mistaken for the real figure). If every token matches, the
prose publishes with a badge naming how many figures were verified. If one
token fails, the whole paragraph is discarded, not edited, and a
deterministic template sentence built directly from the same facts publishes
instead, with a badge saying the model output was blocked. The same fallback
covers an outright API failure or timeout. There is always something correct
to show; the worst case is a boring sentence, never an empty screen or an
invented number.

An identifier like a deal ID `OPP-079` or a period `Q2-2026` is checked as
one token instead: it has to appear in a fact's label or in the restatement,
so the narrator can name a deal it was given and can't name one it wasn't.
[ADR-0008](docs/adr/0008-verifier-checks-identifiers-as-whole-tokens.md) has
the reasoning.

That fallback is not a rare edge case reserved for outages. During
implementation, a live run of "which reps are at risk of missing Q2" had the
narrator write "best-case coverage above 100%", a true statement, but 100 is
the risk threshold, not a fact the narrator was ever handed, so the verifier
blocked the paragraph and the template published instead. That's the system
working as designed: no numeric token gets a pass because it sounds
reasonable.

## Architecture

Load time runs once, cached: read both CSV snapshots, parse dates, melt
quotas into one row per rep per period, join rep attributes onto deals, and
diff the two snapshots into a reconciliation change log.

Query time is a straight line with one early exit: route, validate, compute,
flag, narrate, verify, render. A question no metric covers takes a second
line of the same shape. There's no agent loop, no tool cycle, no
cross-turn state, and no orchestration framework underneath it. Every layer
between the question and the pandas call is a layer that has to survive
being explained to a skeptical executive, and a framework doesn't clear that
bar for a few single-shot model calls.

```
question
  -> router (LLM call 1, tool-forced, catalog-only prompt)
  -> validation (period exists, filters agree, metric/grouping implemented)
  -> metric.compute() (pandas only, produces Facts + a template sentence)
  -> flags (partial period, definitions, data-quality, snapshot divergence, ...)
  -> narrator (LLM call 2, facts only) -> verifier -> Answered | Refused

no metric matched, and not a refused topic:
  -> generator (LLM call 2, tool-forced, schema-only prompt) -> query plan
  -> plan check + run (one frame, pandas written by hand, region withheld)
  -> flags -> narrator (LLM call 3) -> verifier -> Answered (exploratory) | Refused
```

**The catalog is the single source of truth.** It's built by walking the
metric registry plus the loaded data, and it feeds the router prompt, the
validator's enum and coverage checks, the refusal message, and the sidebar's
example questions. Nothing downstream keeps its own copy of the metric list,
so there's one place to look when behavior surprises you, and no example
question can drift out of sync with what the router prompt actually says the
system covers.

**Metrics are self-describing.** Each one is a module under
`acme/metrics/` that registers itself with `@metric`, declaring its
name, description, the groupings it answers at, the intent fields it reads,
the definition keys its answer rests on, and its example questions. The
worked example below adds one from scratch.

**Every number reaches prose through a `Fact`.** A bare float can't carry
the label the narrator's sentence needs (a rep's name in a risk answer, a
quota's period in an attainment one), and giving the model a second,
unchecked channel for labels would give it a place to slip in a number the
verifier never sees. Derived numbers, like a comparison gap or a shortfall
against quota, are precomputed as their own facts too, never left for the
narrator to work out by subtracting two others.

## What it answers

| metric | overall | segment | rep | manager |
|---|---|---|---|---|
| attainment | yes | yes | yes | yes |
| risk | yes | no | yes | no |
| comparison | yes | yes | no | no |
| product_mix | yes | no | no | no |

Attainment is closed-won revenue against quota for a period. Risk is
best-case coverage (closed-won plus open pipeline) per rep, flagging anyone
who can't clear quota even if every open deal closes; the 100 percent
threshold is this system's own invention, and every risk answer says so.
Comparison matches a current period against an earlier one at the same day
of quarter rather than the same calendar date, drawing each side from the
snapshot that owns it and never blending the two. Product mix is closed-won
and open pipeline split by product line, with no quota comparison, since
quotas here are recorded per rep with no product breakdown to divide by;
every deal carries exactly one product-line tag, and the one real
assumption, that a bundled deal would have its whole value counted toward a
single tag, is disclosed on every answer rather than used as a reason to
withhold the number.

One question refuses on purpose. Region refuses because the deal's own
region and its owning rep's home region disagree on 17 of 92 deals in this
data, a count the refusal computes at load time rather than quoting from a
written string. Product line was refused alongside region early on for the
same reason, and that reasoning didn't hold up: unlike region, product line
has no second, disagreeing source to refuse over, just a single clean tag
per deal and an assumption worth disclosing rather than a reason to
withhold. A question outside the catalog goes to the exploratory lane
below. When that lane can't answer either, as with Slack sentiment or
forecasts, which no column covers, the refusal carries the coverage list read
off the same catalog the router prompt uses, plus the reason the exploratory
lane gave. It reads as a boundary the system knows about, not a gap it's
hiding.

## The exploratory lane

A question no metric covers, like loss reasons, stage breakdowns, or top
accounts, doesn't have to dead-end. A third model call fills a structured
query plan: one frame, filters, grouping, one aggregate, sort, and limit. The
model sees column names, kinds, and the values of low-cardinality columns,
never a data row. `acme/query_plan.py` checks the plan against the frame
schemas and runs it with pandas written by hand, so nothing the model writes
ever executes. [ADR-0007](docs/adr/0007-fallback-runs-a-structured-query-plan.md)
covers why this replaced an earlier sandbox that ran model-written pandas.

The figures still come from pandas, and the prose is still verified against
them. What nobody has pinned down is whether the plan asked what the reader
meant. So the answer leads with a red warning, then the query as a plain
English sentence, then the equivalent pandas an analyst can rerun, and it
never gets the verified-metric badge.

A registered metric always wins over this lane, and region stays refused
ahead of both. The region columns are withheld from every plan too, so a
question like "which territory has the most pipeline" can't reach them just
by avoiding the word.

## Conversation memory

A follow-up like "what about SMB?" or "just for Enterprise" is read in light
of the last three questions. What the models remember is how each earlier
question was read, the intent or the query plan, and never what it
answered. The router and the generator have still never been shown a data
figure, so memory gives them nothing to carry forward into a filter or a
restatement.

A follow-up still resolves to a complete reading and says so above the
answer: "Following on from your last question, reading this as attainment
for the SMB segment for Q2-2026." An exploratory refinement shows what
changed from the last query, worked out by comparing the two plans in code.
Refused topics are checked on each new question alone, so "what about the
West?" refuses as region. "New conversation" in the sidebar clears the
memory. The spec is
[`docs/specs/conversation-memory.md`](docs/specs/conversation-memory.md).

## Promoting an exploratory plan

A question that keeps landing in the exploratory lane probably deserves a
metric. Every exploratory attempt is logged locally, and a command line turns
a recurring plan into a metric file:

```bash
python -m acme.promote list
```

`list` groups logged plans that mean the same thing once snapshot, period,
and segment, rep, or manager scope are set aside, most asked first. Then:

```bash
python -m acme.promote promote c70a2dad --name loss_reasons --description "Closed-lost deals in the period, counted by the loss reason the rep recorded." --grouping segment
```

The definition has to be written by a person. The tool refuses an empty one,
a short one, or a copy of its own description of the plan, and it test-runs
the metric for every period and grouping before writing anything. The file
it writes is an ordinary metric under `acme/metrics/`, so after a restart
the question answers in the metric lane with the verified badge. The spec is
[`docs/specs/v3-promote-to-metric.md`](docs/specs/v3-promote-to-metric.md).

## Setup

```bash
git clone <this repo>
cd sales-pipeline-assistant
python -m venv .venv
.venv/Scripts/activate   # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Create a `.env` file at the repo root with an Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Then run the app:

```bash
streamlit run app.py
```

The app works without a key too. Routing falls back to an offline
keyword-based router when the model API is unreachable or unconfigured, and
the interface renders a distinct banner so a live demo degrades instead of
crashing.

Run the test suite with:

```bash
pytest
```

Tests go in through the same seam a user does (`ask(question, data, client)`)
and assert on what reaches the screen, using a stub client shaped like
`anthropic.Anthropic` rather than a live API key, so the suite is
deterministic and free to run.

## Evals

The tests prove the code does what it says with a scripted model. They can't
prove the real models read questions correctly, and a misread question is
the one failure the verifier can't catch, since it still produces a real
number. The evals run 30 questions through `ask` with the real client:

```bash
python -m evals.run --repeat 3
```

Metric questions are scored on the router's reading. Exploratory questions
are scored on their figures against a pandas reference, so two different
plans that compute the same thing both pass. Refusals are scored on nothing
being answered, and for region, on no model being asked at all. Each run
saves its results under `evals/results/` and lists every case whose pass
rate changed since the last one. When the narrator's prose is blocked, the
report shows the draft and the figures that failed, which is how the first
runs found the problems ADR-0008 and the eval regression tests fix.

## Adding a metric: a worked example

Adding a metric means creating exactly one file under `acme/metrics/`
and touching nothing else. Once it's registered, it appears in the router
prompt, the validator's coverage check, the refusal message's coverage list,
and the sidebar's example questions automatically, because all four read off
the catalog rather than off a hand-maintained list.

Say the ask is "what's the average deal size this quarter." Here's the
entire new file, `acme/metrics/average_deal_size.py`:

```python
"""Average deal size: mean closed-won deal value for a period."""

from __future__ import annotations

import pandas as pd

from ..domain import Fact, Result, Unit
from ..periods import bounds, snapshot_for
from ..registry import MetricRequest, metric


@metric(
    name="average_deal_size",
    description="Mean closed-won deal value for a period, overall only.",
    groupings=("overall",),
    intent_fields=("period",),
    definition_keys=("period_membership",),
    examples=("what's the average deal size this quarter",),
)
def average_deal_size(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    snapshot = snapshot_for(period)
    start, end = bounds(period)

    deals = request.data.deals(snapshot)
    rows = deals[deals["period"] == period]
    won = rows[rows["is_won"]]
    average = float(won["deal_value"].mean()) if len(won) else 0.0

    facts = {
        "average_deal_size": Fact(average, Unit.CURRENCY, "Average closed-won deal size"),
        "won_deal_count": Fact(float(len(won)), Unit.COUNT, "Deals closed won"),
    }
    return Result(
        facts=facts,
        table=pd.DataFrame([{"period": period, "average_deal_size": average}]),
        source_rows=won.reset_index(drop=True),
        filters={"snapshot": f"{snapshot} snapshot", "period membership": f"close_date between {start} and {end}"},
        snapshot=snapshot,
        definition_keys=("period_membership",),
        template=f"Average closed-won deal size for {period} is {average:,.0f}, from {len(won)} deals.",
    )
```

That's the whole diff. No edits to `router.py`, `validation.py`, `catalog.py`,
or `app.py`. `registry.discover()` imports every module under
`acme/metrics/` at catalog build time, so dropping this file in is
sufficient for `average_deal_size` to show up as an enum option in the
router's tool schema, as a name the validator will accept, and as an example
question in the sidebar the next time the app runs.

## Models

The router uses `claude-sonnet-5`: a misroute is the one failure the
verifier can't catch, since a wrong metric or a wrong filter produces a
figure that's internally consistent and still answers the wrong question, so
that call gets the stronger model. The narrator uses
`claude-haiku-4-5-20251001`, since writing two or three sentences from a
mapping with arithmetic forbidden is the cheapest task in the system. The
exploratory lane's generator uses the router's model too, since a wrong plan
is a wrong answer in the same way a misroute is. Both IDs live in
`acme/config.py` as named constants, not inline strings, so changing
either model is a one-line edit.
