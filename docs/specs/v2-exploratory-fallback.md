---
title: V2 exploratory fallback lane
triage: ready-for-agent
category: enhancement
---

# V2 exploratory fallback lane

## Problem Statement

V1 refuses everything outside its registered metrics. The refusing is
deliberate and it is most of why the tool is trustworthy, but one response
currently covers two situations that deserve different answers.

Some questions are refused because the data cannot answer them honestly.
Region is the case, and it is the only one: the region on the deal and the
region on the rep who owns it differ on 17 of 92 deals, so any single number
picks a side silently. That refusal is the product working and it stays
exactly as it is.

Everything else is refused only because nobody wrote a metric. Stage
breakdowns, loss reasons, deal size distributions, account-level questions,
rep tenure, and the long tail of one-off analysis are all unambiguous in this
data. A sales leader asking "why are we losing deals?" gets told the system
doesn't cover that, which is true and useless.

An earlier draft of this spec put product line in a third category, refused
because the number was computable but the attribution behind it had never
been agreed. That category turned out not to survive scrutiny. Region refuses
because two definitions measurably disagree, and there is nothing comparable
for product line to disagree with: one clean tag per deal, no nulls, an
identical value set across both snapshots. The attribution argument was an
assumption about how software is sold rather than a finding in the data, and
it was doing the work of a measurement without being one. Product line is now
answered by the `product_mix` metric, which computes the split and discloses
the bundling assumption as a flag rather than withholding the number over it.
The lesson generalized: a refusal has to be earned by the data, and the fact
that one sounds like another is not evidence that it is.

A registry cannot grow fast enough to cover ad-hoc analysis, and a leader who
hits three refusals in a row stops asking, which is the same outcome the old
hallucinating tool produced by a different route.

## Solution

A second lane behind the same question box. When no registered metric covers
a question, a model fills a structured query plan against the frames the
metrics already use: one frame, filters, grouping, one aggregate, sort, and
limit. Code written by hand checks the plan against the frame schemas, runs
it, and presents the result as exploratory rather than as a defined metric.
Nothing the model writes is ever evaluated. ADR-0007 records why this replaced
the generated pandas expression an earlier draft of this spec used.

Every number still comes from pandas. That part does not change and is not
negotiable.

What changes is what is being trusted. In the metric lane, both the
computation and the interpretation are pinned: a registered metric decides
what "attainment" counts, and a human wrote that down. In the fallback lane
the computation is still deterministic, but the interpretation is
model-generated, so the answer carries the query in full and a warning
stated in the strongest terms the interface has. A reader should never have to
guess which lane answered them, and the one that carries more risk is the one
that says so loudest.

Region stays refused ahead of both lanes, with its reason computed from the
data rather than quoted from a written string.

## User Stories

1. As a sales leader, I want a question the registry doesn't cover to be
   answered from the data anyway, so that an unregistered question isn't a
   dead end.
2. As a sales leader, I want an unmissable warning when an answer came from a
   generated query rather than a defined metric, so that I know to check it
   before I repeat it to anyone.
3. As a sales leader, I want the query behind an exploratory answer shown in
   plain English without opening anything, so that the thing I can't
   otherwise check is the thing most in front of me.
4. As a sales leader, I want exploratory answers to carry no verified badge,
   so that the badge keeps meaning exactly one thing.
5. As a sales leader, I want region to keep refusing even though the fallback
   could compute it, so that a deliberate decision isn't quietly reversed by a
   new feature.
6. As a sales leader, I want a question a registered metric covers to be
   answered by that metric rather than by generated code, so that a defined
   business meaning always beats an improvised one.
7. As a sales leader, I want to be told when a question can't be answered from
   the columns that exist, so that I learn the boundary rather than receive a
   confident answer about data nobody has.
8. As a sales leader, I want the row count and the frame an exploratory answer
   read from, so that I can tell a Q1 answer from a Q2 one.
9. As an analyst, I want the query shown as pandas I can run by hand,
   so that I can paste it into a notebook and get the same number.
10. As an engineer, I want a generated plan validated before it runs, so
    that the safety of the lane doesn't depend on the model behaving.
11. As an engineer, I want a rejected plan to refuse rather than be
    repaired, so that the failure mode stays a visible no.
12. As an engineer, I want the fallback to read the same frames the metrics
    read, so that the two lanes can never disagree about what "open" means.
13. As an engineer, I want every fallback attempt logged with its question,
    plan, and outcome, so that V3 has something to promote from.
14. As an engineer, I want the registry consulted first, so that a question a
    metric covers is never answered by generated code.

## Implementation Decisions

### Lane precedence

Four steps, in order, and the first that applies wins:

1. Refused topics short-circuit, before any model call. Region is the only
   one.
2. The router runs against the catalog. A registered metric that validates
   answers in the metric lane, unchanged from V1.
3. Otherwise the fallback lane attempts the question.
4. If the fallback declines or its plan fails validation, the system
   refuses with the catalog coverage hint, as V1 does now, and says why the
   exploratory lane couldn't answer.

Only a question the router can't match reaches step 3. A question it matches
to a metric that doesn't support the requested grouping, like risk by segment,
refuses at step 2 and never reaches the fallback. Answering it there would put
an improvised definition next to a defined one under the same metric name.

The registry is consulted first and always wins. A question a metric covers
must never be answered by generated code, because the metric encodes a
business definition a human agreed to and the generated plan does not.

Refused topics are checked ahead of everything for the reason region is today:
the one wrong move available to a model asked about a refused topic is
silently substituting a nearby column, and that substitution is invisible
downstream because the substituted value is a real one.

### Refused topics

One topic refuses permanently. Its reason is computed at load time rather
than typed into a string, so it cannot go stale against the data.

**Region** refuses because two definitions of it disagree. The deal carries
one, the rep who owns the deal carries another, and they differ on 17 of 92
deals in the current snapshot. Unchanged from V1.

The mechanism stays a table rather than a single hardcoded check, because the
next genuinely ambiguous column should be one entry rather than a refactor.
The table is deliberately hard to add to: an entry needs a measured
contradiction in the data, not a plausible story about one. Product line was
added to it and then removed for exactly that reason, which is recorded in
the Problem Statement above and is the clearest test of the rule this system
has.

Account-level questions were listed out of scope in V1 and are now answerable
through the fallback lane, since accounts carry no equivalent ambiguity.

### What the generator sees

Column names, column kinds, and the distinct values of low-cardinality
columns, in the same shape the router prompt already uses. It never receives
a data row. The generator is structurally incapable of leaking a figure into
its output because it was never shown one, which is the same guarantee the
router rests on and for the same reason.

It never sees a withheld column either. The columns a refused topic rests on,
region on the deal and region on the rep, are left out of the prompt, the
tool schema, and every row listing, and a plan naming one is rejected as
withheld. Refusing the word "region" ahead of routing isn't enough on its own,
since "which territory has the most pipeline" never says it.

If a question needs a column that does not exist, the generator returns a
decline with a reason instead of a plan. Declining is cheap. A plan over a
column nobody has is a refusal one step later anyway, and a plausible-looking
substitution is worse than either. The decline reason reaches the reader on
the refusal.

### The query plan

Recorded in ADR-0007. The generator fills a plan through a forced tool whose
schema enumerates the frames and columns:

- `frame`: exactly one of the frames below.
- `filters`: column, operator, and value, combined with AND. Ordered
  comparisons only on number and date columns. A category filter must name a
  value the column holds, so a typo refuses instead of matching nothing.
- `group_by`: up to two columns, never a number column.
- `aggregate`: count, distinct count, sum, mean, median, min, or max. Leaving
  it out lists rows instead, with the columns the plan names.
- `sort_by`, `descending`, and `limit`, capped at the row cap.

`acme/query_plan.py` checks every field against the schema of the frame
the plan names, then runs the plan with pandas written by hand. A rejected
plan refuses. It is never repaired, never partially run, and never retried
with the offending part removed, because a repaired query answers a question
nobody asked.

Every result carries two readings of the plan, both built from the plan
itself and never from model prose. One is a plain English sentence for the
reader. The other is the equivalent pandas for an analyst, and tests pin that
code to the result that actually ran.

A result larger than a row cap is truncated for display with the full count
reported.

### Frames the lane may name

`deals_q1`, `deals_q2`, `quotas`, and `reps`, bound to the same objects the
metrics use. A plan names exactly one, so there is no way to blend the two
snapshots, which would reintroduce the exact error the reconciler exists to
prevent.

### Facts, narration, and the badge

The result is converted into Facts the same way a metric's is, so the narrator
still sees only computed values and the verifier still checks every numeric
token in the prose against them. The no-hallucinated-number guarantee is
unchanged in this lane.

What is not guaranteed is that the plan answered the question that was
asked. That is why the badge differs. A verified metric answer says how many
figures were checked. An exploratory answer says the figures were computed and
checked but the query was model-written, and it shows the query.

The `Answered` variant grows a lane marker rather than a parallel type, so
every consumer that already handles an answer keeps working and the interface
decides what to draw from one field.

### Presentation

Exploratory answers render in the same two-column layout, led by a warning in
the strongest treatment the interface has: red, above the answer rather than
below it, and impossible to read past. It says the answer did not come from a
defined metric in the catalog, that the query was written by a model, and that
the figure should be checked before being repeated.

Under the warning: the query in plain English, then its pandas, both shown
expanded and never behind a
click, the result table, the row count, and the frame that was read.

The warning is the one place in this app where alarm is the correct register.
Everywhere else the interface works to make caveats legible without making
them frightening, because a leader who is alarmed by a partial-period notice
stops reading notices. Here the risk is real and specific, a model wrote the
query, so the treatment matches.

The four detail sections stay as they are. Flags still run, so partial period,
stale close dates, and the rest still apply to an exploratory answer, since
those caveats are properties of the data rather than of the lane.

### Query log

Every fallback attempt appends a record: the question, the generated
plan, whether validation passed, whether execution succeeded, and the
row count. This is what V3's promote-to-metric path reads, and it is the
cheapest possible thing that makes V3 possible, so it ships now rather than
being retrofitted onto a lane that has already been answering questions.

The log is append-only and local. No question text leaves the machine.

### Models

The generator uses the router's model, `claude-sonnet-5`, from the same
configuration constant. Filling a query plan against a schema is closer in
kind to routing than to narrating, and a wrong plan is a
wrong answer, so it gets the stronger model.

## Testing Decisions

The primary seam stays `ask(question, data, client)`. Fallback answers are
asserted through it the same way metric answers are.

The query plan checker is a deliberate second seam, tested directly, for the
same reason the reconciler's change log was in V1: it is the highest-risk code
in the lane and getting it wrong reproduces a failure worse than the one the
project exists to prevent. Its tests try to get a bad plan past it: unknown
frames and columns, withheld columns, aggregates over the wrong column kind,
ordered comparisons on text, category values the column doesn't hold,
malformed dates, and code smuggled into a filter value. A second set pins the
displayed pandas to the result that actually ran.

Covered through the primary seam:

- A product-line question answers in the fallback lane with a table.
- A question a metric covers is answered by the metric lane, never the
  fallback, asserted by the lane marker.
- Region refuses and no generation is attempted.
- A question needing a column nobody has refuses rather than answering.
- An exploratory answer carries no verified-metric badge and does carry its
  query, in plain English and as pandas.
- A payload in the old expression shape, including the two that escaped the
  V2 sandbox, refuses and runs nothing.
- A plan over either region column refuses as withheld.
- A decline or a rejected plan says why on the refusal.
- Prose in the fallback lane is still verified against facts, asserted by
  stubbing prose containing an unlisted figure and seeing it blocked.
- The two snapshots are never blended, since a plan names exactly one frame.
- Every fallback attempt appends exactly one log record, including refusals.

## Out of Scope

Promote-to-metric, which is V3 and is what the query log exists to feed.

Writes of any kind. Joins the metric lane doesn't already make available.
Multi-turn refinement of a generated plan. Charts over exploratory
results, since a chart implies a settled shape and these do not have one.

Region, permanently, on the grounds in Refused topics above. It remains a
refusal in V2 even though the fallback lane could compute it, which is the
point: a lane that can answer anything is exactly the lane most likely to
answer something it shouldn't.

## Further Notes

### Planned for V3

A promote-to-metric path: a fallback query that keeps recurring in the log gets
turned into a registered metric, with the recorded plan as the starting
point for the metric body and a human writing the definition text before it
ships. The point of V3 is that the human writes the definition, so the
promotion is a decision rather than a copy.

### Stack

No new dependencies. The plan is a pydantic model and the frames already
exist. `duckdb` and `sqlglot` are not adopted, per ADR-0006.

The vocabulary used throughout this spec is defined in `CONTEXT.md` at the
repo root.
