# Acme pipeline assistant

A Streamlit chat app for a sales leader who wants a plain-English answer
about pipeline and quota, with the figures, the source rows, and every
assumption laid out next to it.

The previous AI reporting tool at Acme invented a number in front of the
CCO, and it's unusable now regardless of how often it happens to be right.
This one is built so that failure mode can't recur: the language model is
used exactly twice per question and never produces a number.

## The trust argument

The model is called exactly twice per question, and neither call touches a
data row on the way to producing a figure.

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
flag, narrate, verify, render. There's no agent loop, no tool cycle, no
cross-turn state, and no orchestration framework underneath it. Every layer
between the question and the pandas call is a layer that has to survive
being explained to a skeptical executive, and a framework doesn't clear that
bar for two single-shot model calls.

```
question
  -> router (LLM call 1, tool-forced, catalog-only prompt)
  -> validation (period exists, filters agree, metric/grouping implemented)
  -> metric.compute() (pandas only, produces Facts + a template sentence)
  -> flags (partial period, definitions, data-quality, snapshot divergence, ...)
  -> narrator (LLM call 2, facts only) -> verifier -> Answered | Refused
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
withhold. Anything outside the catalog entirely (Slack sentiment, forecasts,
account-level questions) refuses with the coverage list read off the same
catalog the router prompt uses, so the refusal reads as a boundary the
system knows about, not a gap it's hiding.

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
mapping with arithmetic forbidden is the cheapest task in the system. Both
IDs live in `acme/config.py` as named constants, not inline strings, so
changing either model is a one-line edit.
