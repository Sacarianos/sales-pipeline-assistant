---
title: V1 Acme pipeline assistant
triage: ready-for-agent
category: enhancement
---

# V1 Acme pipeline assistant

## Problem Statement

A sales leader at Acme needs to ask plain-English questions about pipeline
and get answers they can repeat in a meeting without being contradicted.

They can't do that today. The previous AI reporting tool invented numbers, their
CCO caught it in front of the room, and the tool is now unusable regardless of
whether any given answer happens to be right. The trust problem outlived the
accuracy problem.

Underneath that sits a second problem the old tool never surfaced. The data
itself disagrees with the data. Q1 closed-won reads 6,041,000 in the snapshot
frozen at Q1 close and 4,050,000 in the current Q2 snapshot, a gap of 1,991,000
that no dashboard explains. Some of that gap is deals that genuinely came unwon.
Most of it is thirteen deal IDs that now point at completely different accounts,
which any straightforward join misreads as revenue reversal. A tool that answers
"what was Q1?" with a single confident number is wrong no matter which number it
picks.

## Solution

A Streamlit chat app where a sales leader asks a question and gets back a direct
answer, the figures behind it, the actual deal rows, and an explicit list of
every assumption the answer rests on.

The language model is used exactly twice and never produces a number. Once to
turn the question into a structured intent, once to write prose around figures
it was handed. Every number is computed by pandas. A verifier reads each numeric
token out of the model's prose and blocks the whole paragraph if any of them
fails to match a computed value, falling back to a deterministic sentence that
is boring and correct.

When the two snapshots disagree, the app says so, names the deals responsible,
and distinguishes a deal that came unwon from a deal ID that was reused. When a
question needs data the system can't answer honestly, it refuses and says what
it does cover. Region questions are refused in V1 by design, because two
definitions of region exist in this data and they disagree on 17 of 92 deals.

## User Stories

1. As a sales leader, I want to ask "how is the Enterprise segment tracking
   against quota this quarter?" in plain English, so that I don't have to learn
   a query language or find the right dashboard.
2. As a sales leader, I want a direct numeric answer in the first sentence, so
   that I can read it aloud in a meeting without hunting for the point.
3. As a sales leader, I want to see the exact figures the answer used, so that I
   can quote a specific number rather than a paraphrase.
4. As a sales leader, I want to see the actual deal rows behind every answer, so
   that I can spot a deal I know is wrong before anyone else does.
5. As a sales leader, I want to see the row count and the filter that produced
   the rows, so that I know whether the answer covers what I meant.
6. As a sales leader, I want the system to restate my question back to me in one
   sentence inside the answer itself, so that a misread question is obvious
   without me opening anything.
7. As a sales leader, I want every assumption the answer depends on listed where
   I can see it, so that I'm never surprised by one in front of my CCO.
8. As a sales leader, I want to be told when I'm looking at a partial period, so
   that I read 4.5% attainment as "day 32 of 91" and not as a catastrophe.
9. As a sales leader, I want the business definition behind each metric spelled
   out in plain English, so that I know what "attainment" counts and what it
   excludes.
10. As a sales leader, I want to know which of the two snapshots answered my
    question, so that I can explain why my number differs from someone else's.
11. As a sales leader asking about Q1, I want the as-reported figure to lead with
    the restated figure shown next to it, so that I get the number the business
    committed to and the number the current data supports at the same time.
12. As a sales leader, I want the gap between as-reported and restated broken
    into its causes, so that I can tell a genuine unwin from a data-quality
    artifact.
13. As a sales leader, I want deals whose IDs were reused between snapshots
    labelled as reused rather than unwon, so that I never announce a revenue
    reversal that didn't happen.
14. As a sales leader, I want to know when a deal I'm looking at changed between
    the two snapshots, so that I understand why my recollection differs from the
    screen.
15. As a sales leader, I want open deals with a close date already in the past
    flagged, so that I know part of my pipeline is stale before I forecast on it.
16. As a sales leader, I want a warning when a headline number rests on fewer
    than five deals, so that I don't treat a small sample as a trend.
17. As a sales leader, I want to be told when a field the answer depends on has
    missing values, so that I can judge whether the gap matters.
18. As a sales leader, I want to ask "which reps are at risk of missing Q2?" and
    get a list, so that I know who to talk to this week.
19. As a sales leader, I want the risk threshold explained as our invention
    rather than a Acme standard, so that I don't misrepresent it as company
    policy.
20. As a sales leader, I want risk measured as best-case coverage rather than
    pace, so that the list means "cannot make quota even if everything closes"
    instead of flagging nearly everyone in a young quarter.
21. As a sales leader, I want the reps who clear quota named in the prose, so
    that the good news is as legible as the bad.
22. As a sales leader, I want the org-level best-case total and the shortfall
    against quota, so that I know the size of the problem and not just its shape.
23. As a sales leader, I want to ask "how does Q2 attainment compare to where we
    were at the same point in Q1?" and get a same-day-of-quarter comparison, so
    that I'm not misled by comparing a third of a quarter to a whole one.
24. As a sales leader, I want the comparison to explain that Q1 was backloaded,
    so that I understand a 13-point gap at day 32 doesn't project to a 13-point
    gap at quarter end.
25. As a sales leader, I want each side of a cross-quarter comparison drawn from
    its own snapshot and never blended, so that the comparison is internally
    consistent.
26. As a sales leader, I want to ask a question without naming a quarter and have
    it answered for the current one, so that ordinary phrasing works.
27. As a sales leader, I want the assumed quarter stated in the restatement when
    I didn't name one, so that a wrong default is visible immediately.
28. As a sales leader, I want a refusal when I ask about region, naming the two
    conflicting definitions and how many deals they disagree on, so that the
    refusal reads as a deliberate design decision rather than a gap.
29. As a sales leader, I want a refusal when I ask about something outside the
    system entirely, listing what it does cover, so that I learn the boundary
    instead of guessing at it.
30. As a sales leader, I want the system to refuse rather than answer a nearby
    question it can handle, so that I never get a confident answer to a question
    I didn't ask.
31. As a sales leader, I want a badge telling me how many figures in the prose
    were verified against computed values, so that I have a visible reason to
    trust the paragraph.
32. As a sales leader, I want the model's prose discarded entirely when any
    figure fails verification, so that a partially-wrong paragraph never reaches
    me.
33. As a sales leader, I want a plain computed summary when the prose is
    discarded, so that a verification failure costs me style and not the answer.
34. As a sales leader, I want to be told when the answer was routed without the
    language model, so that I check the restatement more carefully during an
    outage.
35. As a sales leader, I want the app to keep working when the model API is
    unreachable, so that a live demo degrades instead of crashing.
36. As an analyst, I want every figure on screen to be reproducible by hand from
    the source rows, so that I can verify the tool rather than trust it.
37. As an analyst, I want the period membership rule stated explicitly, so that I
    know which quarter a given deal counts toward before I recompute anything.
38. As an analyst, I want the quota source named, so that I reconcile against the
    same file the tool used.
39. As an analyst, I want to see the structured intent the router produced, so
    that I can tell a computation error from a routing error.
40. As an analyst, I want the reconciliation change log available, so that I can
    audit which deals moved between snapshots and how.
41. As an engineer, I want to add a new metric by editing exactly one file, so
    that the system is extensible rather than a demo.
42. As an engineer, I want a newly registered metric to appear automatically in
    the router prompt, the validator, the refusal message, and the sidebar
    examples, so that I can't ship a metric that's half-wired.
43. As an engineer, I want the catalog to be the single source of truth for what
    the system can answer, so that there's one place to look when behavior
    surprises me.
44. As an engineer, I want the model to be structurally incapable of seeing a
    data row at routing time, so that the no-hallucinated-numbers guarantee
    doesn't rest on prompt wording.
45. As an engineer, I want an unrecognized deal stage to count as open and raise
    a flag, so that next quarter's new stage name doesn't silently shrink a
    number.
46. As an engineer, I want the reconciler to find changed deals by diffing rather
    than by a hardcoded list of IDs, so that it still works on next quarter's
    snapshot.
47. As an engineer, I want validation failures to return a refusal rather than a
    nearest-match guess or a loosened retry, so that the failure mode is always
    a visible no.
48. As an engineer, I want conflicting filters caught before computation, so that
    an impossible question refuses instead of silently answering a different one.
49. As an engineer, I want every number the prose may contain to exist as a
    named fact, including derived gaps and labels like the day of quarter, so
    that the verifier has no pattern-based exemptions to defend.
50. As an engineer, I want a deterministic fallback sentence attached to every
    result, so that there is always something correct to display.

## Implementation Decisions

### Layering

Load time is cached and runs once. It reads the CSVs, normalizes types, melts
quotas into long format, joins rep attributes onto deals, diffs the two
snapshots into a change log, and builds the catalog from the metric registry plus
the loaded data.

Query time is a straight line with one early exit: router, validation,
computation, flags, narration, verification, render. Both model calls are
single-shot. There is no agent loop, no tool cycle, and no cross-turn state, so
no orchestration framework is used. LangChain and LangGraph are explicitly
rejected. Every layer between the question and the pandas call is a layer that
has to be explained to a skeptical executive.

Business definitions live in their own module, separate from the metrics that
reference them, so the plain-English text shown to the user is not buried in
computation code.

### Data loading

`data/Q2/reps.csv` is the quota source for both quarters. Its `quota_q1_2026`
column is byte-identical to the same column in `data/Q1/reps.csv`, verified by
diff, so quotas were not restated between snapshots and using one file loses
nothing. `data/Q1/reps.csv` has no `quota_q2_2026` column at all. Q1 quota totals
5,920,000 and Q2 totals 6,200,000.

Dates parse to date objects. Stage strings normalize. Quotas melt to one row per
rep per period.

### Period membership

A deal belongs to the quarter its `close_date` falls in, whether the deal is
open or closed. No other date field determines period. This is the only rule the
data supports, since the Q1 snapshot's 25 open deals all carry Q2 close dates and
the Q2 snapshot carries 40 deals with Q1 close dates. The rule applies uniformly
to closed-won revenue, open pipeline, and best-case coverage.

### Open deals

Open is the complement of `Closed Won` and `Closed Lost`, not a maintained list
of open-stage names. The two snapshots use different open-stage vocabularies:
Q1 has `Prospecting` and no `Negotiation`, Q2 the reverse. A whitelist that
someone forgets to update would silently drop deals from best-case coverage and
make a number quietly too low with no flag. The complement fails loudly instead.
A registry of known stage names exists solely to raise an unknown-stage flag when
the loader meets a name it hasn't been told about. Closed-won and closed-lost are
the only two stage names the system hardcodes.

### Reconciliation

An outer join on `deal_id` produces a change log with one row per deal per
changed field, carrying the deal ID, change type, field, Q1 value, and Q2 value.

Change types: `new_in_q2`, `unwon`, `reopened`, `drifted`, `id_reused`,
`unchanged`.

ID reuse is detected when both `account_name` and `created_date` change for the
same ID, and it takes precedence over `unwon` and `drifted` for that row. This is
recorded in ADR-0001. Thirteen IDs in this dataset match the rule, and twelve of
them would otherwise be classified as unwon, misreporting 1,220,000 as revenue
reversal. Detection is generic and no deal IDs are hardcoded anywhere in the
system, so the reconciler survives next quarter's snapshot.

The true decomposition of the 1,991,000 Q1 gap is four genuine unwins worth
363,000, twelve reused IDs worth 1,220,000, and the remainder from deals whose
close date crossed the quarter boundary.

### Catalog and registry

Metrics are self-describing modules registered by decorator, carrying a name,
description, the intent fields they accept, their definition keys, and example
questions. The catalog is built by walking the registry plus the loaded data, and
it is the single source of truth feeding the router prompt, the validator's enum
and coverage checks, the refusal message, and the sidebar examples.

Adding a metric requires editing exactly one file. This is a hard requirement.

The catalog carries the metric list, groupings, segments, reps, managers,
periods, and the as-of date. `as_of` is a configuration constant pinned to
2026-05-02 and is never derived from the current date.

### Router

Anthropic tool use with a single tool whose input schema is the JSON schema of
the intent model, enums populated from the catalog, and tool choice forced to
that tool. Not free-form JSON in a text reply.

The router receives column names and the distinct values of low-cardinality
columns. It never receives a data row, so it is structurally incapable of leaking
a number.

The intent carries metric, grouping, period, comparison target, segment, rep,
manager, a one-sentence restatement of how the question was read, and an
optional unsupported reason.

If a question needs a metric, segment, or rep not in the catalog lists, the
router sets the metric to unsupported and explains why. It does not substitute
something close.

When a question doesn't name a quarter, the period defaults to the quarter
containing the as-of date, and the restatement says so explicitly. This is
recorded in ADR-0005. Refusal stays reserved for unknown metric, unknown segment
or rep, and region.

An offline keyword-based router is the fallback when the model call fails, so a
network outage degrades instead of crashing. The offline path renders a distinct
banner, still populates the restatement from the intent it built, and is allowed
to return unsupported when keyword matching is ambiguous. This is recorded in
ADR-0004. Refusing is cheap and a wrong route is expensive, and a misroute is
the one failure the verifier cannot catch.

### Validation

The intent is validated by the model first, then by the checks the model can't
express: the period exists in the catalog; any pair of set filters among rep,
segment, and manager must agree via the rep-to-segment and rep-to-manager lookup;
a comparison requires a comparison target; risk requires a period still in
progress; and the metric-grouping pair must be implemented.

The filter-agreement check is one generalized rule over all three pairs rather
than three near-duplicate checks. Manager is a strict function of segment in this
data, so a manager-segment mismatch is exactly as nonsensical as a rep-segment
one, and silently dropping one of two filters would answer a different question
than the one asked.

Any failure returns a refusal carrying a reason and a catalog hint. Never a
nearest-match guess, never a retry that loosens the constraint.

### Metrics

Four metrics in V1, all returning the same result shape: a facts mapping, an
aggregate table, the source rows, the literal filters applied, the snapshot that
answered, the definition keys, and a deterministic template sentence.

Implemented metric and grouping pairs:

| metric | overall | segment | rep | manager |
|---|---|---|---|---|
| attainment | yes | yes | yes | yes |
| risk | yes | no | yes | no |
| comparison | yes | yes | no | no |
| product_mix | yes | no | no | no |

Risk is inherently per-rep. A segment-level or manager-level risk number would
be a sum of rep best-cases against a summed quota, which hides the individual
shortfall the metric exists to surface. Comparison ships overall and by segment
in V1. Product mix answers overall only: it already breaks its answer out by
every product line at once, the way risk breaks out by every rep, so there is
no separate "by segment" or "by rep" slice to add on top of that.

**Snapshot routing.** Questions about Q1 read the Q1 snapshot as reported and
also compute the restated figure from the Q2 snapshot. Questions about Q2 read
the Q2 snapshot only. A Q1-versus-Q2 comparison draws each side from its own
snapshot and never blends them. Stage is reported only within the snapshot that
owns it, so there are no cross-snapshot stage comparisons.

**Attainment** is closed-won revenue divided by quota for the period, with open
pipeline excluded. Best-case and win-rate-weighted figures are computed as
separate named facts and never folded into the attainment number.

**Risk** is best-case coverage: closed-won plus open pipeline against quota, per
rep, with both sides filtered by period membership. Anyone below 100 percent is
flagged, meaning they cannot make quota even if every open deal closes. A
pace-based rule is explicitly rejected, since at day 32 seven of ten reps have
closed nothing and pace would flag almost everyone.

**Comparison** matches the same day of quarter rather than the same calendar
date. Day 32 of Q2 is May 2 and day 32 of Q1 is February 1.

**Product mix** is closed-won revenue and open pipeline for a period, split by
product line, with no quota comparison, since this data records quota per rep
and has no per-product breakdown to divide by. Every deal carries exactly one
product-line tag, a verified fact with no nulls and an identical value set
across both snapshots; whether that tag reflects a strict one-product-per-deal
rule or a convention for recording a bundled deal is not something the file
confirms either way, and the `product_line_attribution` flag says so on every
answer rather than being a reason to withhold the number.

There is no standalone deal-count metric. Counts appear as supporting facts
inside currency answers.

### Facts

`Result.facts` maps a name to a fact value object carrying a value, a unit
(currency, percent, count, or date), and a human label. A bare float mapping
can't carry the labels the prose needs, such as rep names in the risk answer.
Adding a separate unchecked labels channel would give the model a place to
introduce a number the verifier never sees. This is recorded in ADR-0002.

The verifier reads only the value, so the guarantee is unchanged, and the unit is
what lets the verifier know that an 8 in "8 of 10 reps" is a count while 4.5 is
a percent.

Facts are the contract for the whole system. The narrator sees only facts. The
verifier checks only against facts. A number absent from facts cannot legally
reach the screen.

Derived numbers are facts too. A gap, delta, or margin stated in prose is
precomputed as its own fact and never left for the narrator to subtract from two
other facts, since the model is forbidden from arithmetic and not merely from
inventing figures outright.

For the risk metric, facts carry the org rollup plus one fact per rep who clears
100 percent best-case, keyed by rep and labelled with the rep's name. Reps below
100 percent appear in the table and source rows and are never named in prose.
This scales with the interesting case rather than with headcount.

Values that look like prose furniture are facts as well: the period year, the day
of quarter, and the days in quarter. This is what lets the verifier run with no
pattern-based exemptions.

### Flags

A list of rule functions, each taking a result, an intent, and context, and
returning a flag or nothing. All rules run and all results are collected, because
the list itself is displayed in the UI rather than being buried as conditionals
inside metrics.

Rules: partial period, definition text for each definition key, invented-rule
disclosure for risk, snapshot divergence with the deals responsible, changed
deals joined against the change log, stale close date for open deals at or before
the as-of date, small sample below five deals behind a headline number, missing
values in a field the answer depends on, and unknown stage.

The snapshot divergence flag reports the as-reported and restated figures and
decomposes the gap into genuine unwins and reused IDs, quoting each count and
value separately.

### Narration

The narrator receives the question, the restatement, and the facts. Nothing else.
Not the dataframe, not the source rows, not the flags.

Prompt rules: use only the supplied figures, write them in full with no shorthand,
do not round or recompute or introduce any number not listed, two or three
sentences, lead with the answer, do not hedge, and do not suggest checking a
dashboard.

### Verification

Every numeric token is pulled out of the prose by regex and stripped of currency
symbols, separators, and percent signs. The allowed set is built from the facts,
including honest variants, and compared within a small tolerance.

Variant generation is scoped by unit. Division by a thousand and by a million
applies to currency facts only. Percent, count, and date facts get rounding
variants at whole, one decimal, and two decimals, and nothing else. Without this
scoping the verifier would silently accept "1,991" as shorthand for 1,991,000.

No numeric token is exempt by pattern. Values that appear in prose but aren't
metric outputs are supplied as facts instead of carved out of the check, so the
rule stays absolute and has no exceptions to defend. This is recorded in
ADR-0003.

When every token matches, the prose publishes with a badge naming the verified
count. When any token fails, the prose is discarded entirely and the result's
template sentence publishes with a badge saying the model output was blocked.

The template fallback also covers an outright narrator API failure or timeout,
not only a verification failure. One fallback path, two triggers. The fallback
always exists, so the worst case is a boring correct answer rather than an error
or an empty screen.

### Interface

Two columns of equal width. Chat on the left, inside a fixed-height transcript
so it reads as a chat window rather than a page that grows without end. The
right panel has four stacked sections, all visible without clicking: the
computed figures, the flags, the source rows with the filter and row count, and
a trace showing the intent and the answering snapshot.

The restatement renders inside the answer itself and not in the trace panel. It
is the only backstop against a silent misroute, so a human has to see it without
opening anything.

The figures section leads with a chart, and the flags section renders the
caveats specific to an answer ahead of the static definitions it rests on.
Everything stays on screen either way. Density is a typography problem here,
never a visibility one, because an assumption behind a click is the exact
surprise the panel exists to prevent, and a wall of undifferentiated text
defeats that goal as thoroughly as hiding would.

Sidebar example questions are buttons that ask the question rather than quoted
text the reader has to retype, and like the refusal message they are read from
the catalog.

Prose renders word by word as it publishes. Nothing streams from a model call:
the narrator's paragraph is complete and verified before the first word appears,
so the effect replays text already final and cannot show a figure ahead of the
verifier.

### Models

The router uses `claude-sonnet-5`, because a misroute is the one failure the
verifier cannot catch, so that call gets the better model. The narrator uses
`claude-haiku-4-5-20251001`, since writing three sentences from a mapping with
arithmetic forbidden is the cheapest task in the system. Both model IDs live in
a configuration constant. Opus and Fable are explicitly not used, since frontier
models don't outperform on constrained extraction and the extra latency hurts a
live demo.

### Refusals

The region refusal computes its own numbers at load time rather than quoting a
written string. It reports how many deals have a region on the deal record that
disagrees with the region on the rep record, currently 17 of 92, and notes that
one deal's region changed between snapshots. A number the system derived from
the files it just read is worth more than the same number typed by hand.

Segment carries no equivalent ambiguity. Deal segment matches rep segment on all
180 rows across both files, which is why segment is answerable while region is
not.

The out-of-scope refusal reads its list from the catalog so that it sounds
intentional rather than apologetic.

## Testing Decisions

A good test here asserts external behavior only. It goes in through the same door
a user does, with a question string, and asserts on what reaches the screen. It
does not reach into a metric function, a flag rule, or the verifier directly, and
it does not assert on the shape of intermediate structures that the design may
still move.

There is no prior art in this repo. It contains data and documentation and no
code, so both seams below are new and are proposed at the highest point they can
sit.

### Primary seam

One function taking a question string, the loaded data, and an injected model
client, returning an answer. Router, validation, computation, flags, narration,
and verification all sit behind it. The client being a parameter is what makes
the two model calls testable, since a stub returns whatever tool-use input or
prose a given case needs.

The answer is a discriminated union of answered and refused. The answered variant
carries the prose, which source it came from, verified figure counts for the
badge, the facts, the flags, the aggregate table, the source rows, the filters,
the snapshot, the full intent including the restatement, and whether the router
ran online or offline.

Everything reachable from this seam is tested here:

- The three acceptance cases, asserted on facts from the question string.
- Both refusal cases, asserted as a refused answer with the expected reason.
- Verification success, asserted on the badge count.
- Verification failure, by stubbing prose containing a figure absent from facts,
  asserting the prose is discarded and the template publishes.
- Currency-only variant scoping, by stubbing prose containing a thousands
  shorthand of a currency fact and asserting it is blocked.
- Narrator API failure, by stubbing a raise, asserting the template publishes.
- Offline routing, by stubbing a router failure, asserting the banner appears and
  the restatement is populated.
- The metric and grouping matrix, as a table of calls that each either answer or
  refuse.
- Filter conflict refusals across all three filter pairs.
- Default period resolution, asserting the restatement names the assumed quarter.
- Flag presence for partial period, invented rule, stale close date, small
  sample, missing field, and snapshot divergence.

### Secondary seam

The change log produced by the loader, used only for the reconciliation matrix.
It is reachable through the primary seam, but only for the deals whose source
rows a given question happens to touch, so asserting the whole matrix is direct
here and contorted anywhere else. This seam covers the four genuine unwins, the
twelve reused IDs, the four deals new in Q2, the reopened deal, the region drift,
and the single value drift outside the reused set.

This is a deliberate exception to the external-behavior rule. The ID reuse logic
in ADR-0001 is the highest-risk code in the system, and getting it wrong
reproduces the exact failure the project exists to prevent, so it is tested head
on rather than inferred.

### Not seams

Individual metric functions, individual flag rules, the verifier, and the router
are deliberately not test seams. Each is reachable from the primary seam, and
pinning them separately would lock in implementation shape that the fact keying
and the grouping matrix may still move.

The loader is a fixture rather than a seam. It runs once per test session and
feeds the data argument into the primary seam.

### Reference values

These came from independent computation against the CSVs and are the expected
values for the acceptance cases.

- Q1 closed-won as reported: 6,041,000 at 102.0 percent of a 5,920,000 quota.
- Q1 closed-won restated from the Q2 snapshot: 4,050,000 at 68.4 percent.
- Day 32 of Q1: 1,260,000 across 10 deals at 21.3 percent, identical in both
  snapshots.
- Q2 Enterprise: 165,000 closed against a 3,650,000 quota at 4.5 percent, with
  3,600,000 open.
- Q2 organization: 518,000 closed at 8.4 percent, best case 5,716,000 against a
  6,200,000 quota, short by 484,000.
- Reps clearing 100 percent best case: Marcus Rivera at 132.4 percent and James
  Okafor at 124.7 percent. Eight of ten fall below, with Tom Bradley closest at
  98.7 percent.
- Q1 win rate by value: 77.9 percent in the Q1 snapshot, 79.4 percent in the Q2
  snapshot.
- Region mismatches: 17 of 92.
- Stale open deals as of 2026-05-02: two.
- Closed-lost deals missing a loss reason: one of nine.
- Q2 closed-won by product line: Analytics Add-on 138,000, Core Platform
  295,000, Security Module 85,000, summing to the known 518,000 org total.

## Out of Scope

Region questions and account-level questions. Forecasts and anything
forward-looking. Any period outside Q1-2026 and Q2-2026. Multi-turn
follow-ups. Authentication. Write-back to any source system.

Product line was excluded from the original V1 cut alongside region, on the
same reasoning, and that reasoning does not hold up: region refuses because
two definitions of it actively disagree in the data, while product line has
no such disagreement to refuse over. Every deal carries exactly one clean
`product_line` value, no nulls, identical value sets across both snapshots.
The `product_mix` metric reports closed-won and open pipeline split by
product line, with no quota comparison, since quotas in this data are
recorded per rep and carry no product breakdown to divide by. The one real
assumption, that a bundled deal (if one exists) would have its whole value
assigned to a single tag, is disclosed on every answer by the
`product_line_attribution` flag rather than used as a reason to withhold the
number. Computing a number and disclosing its assumption is the position
this project's whole design otherwise takes; refusing here was an
inconsistency, not a cut earned by the data.

Charts were excluded from the original V1 cut and are now in, one per metric,
under a rule that keeps the exclusion's intent: the view layer computes
nothing. A chart may only plot a value that is already a Fact or a column of
the aggregate table the metric returned, so it is a second rendering of an
answer and never a second source for one. A metric with no chart registered
renders without one, which is what keeps the one-file rule above intact.
`tests/test_charts.py` enforces this against the data bound to every chart.

Rep-level comparison and segment-level or manager-level risk are out of scope for
V1 per the grouping matrix.

The out-of-scope list is read from the catalog by the refusal message rather than
being written as prose in two places.

## Further Notes

### Planned for V2

A text-to-SQL fallback lane over DuckDB for questions the registry doesn't cover,
with `sqlglot` validating that the generated statement is a single read-only
select against whitelisted tables. Results get a visually distinct treatment
marking them exploratory rather than a defined metric, with the SQL shown
expanded, and they never receive the same verified badge.

A promote-to-metric path so that a logged fallback query which keeps recurring
can be turned into a registered metric.

Neither is built now. The V1 design should avoid choices that would make them
expensive later, which is part of why the result shape carries its filters and
snapshot explicitly and why the catalog is the single source of truth.

### Stack

`anthropic`, `pydantic`, `pandas`, and `streamlit`. `duckdb` and `sqlglot` arrive
with V2.

### Decisions recorded as ADRs

ADR-0001 ID reuse detection. ADR-0002 the fact value object. ADR-0003 verifier
pattern exemptions. ADR-0004 offline router visibility. ADR-0005 default period
resolution.

The vocabulary used throughout this spec is defined in `CONTEXT.md` at the repo
root.
