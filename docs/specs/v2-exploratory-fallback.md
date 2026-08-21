---
title: V2 exploratory fallback lane
triage: ready-for-agent
category: enhancement
---

# V2 exploratory fallback lane

## Problem Statement

V1 answers three metrics and refuses everything else. The refusing is
deliberate and it is most of why the tool is trustworthy, but one response
currently covers three situations that deserve different answers.

Some questions are refused because the data cannot answer them honestly.
Region is the case: the region on the deal and the region on the rep who owns
it differ on 17 of 92 deals, so any single number picks a side silently. That
refusal is the product working and it stays exactly as it is.

Some are refused because the number is computable but the method behind it has
never been agreed. Product line is the case, and it is worth being precise
about why, because the data itself is clean. There are no nulls in either
snapshot, the value set is identical across both, and every cross-snapshot
change is explained by ID reuse the reconciler already detects. What is not
settled is attribution: every deal carries exactly one product line, so a
product-line total assigns that deal's entire value to a single product. If
deals span products, that overstates one and understates the others. Until
somebody decides whether that attribution is right, the honest output is a
refusal that says so.

The rest are refused only because nobody wrote a metric. Stage breakdowns,
loss reasons, deal size distributions, account-level questions, rep tenure,
and the long tail of one-off analysis are all unambiguous in this data. A
sales leader asking "why are we losing deals?" gets told the system doesn't
cover that, which is true and useless.

A registry cannot grow fast enough to cover ad-hoc analysis, and a leader who
hits three refusals in a row stops asking, which is the same outcome the old
hallucinating tool produced by a different route.

## Solution

A second lane behind the same question box. When no registered metric covers
a question, the system generates a single pandas expression against the frames
the metrics already use, validates that expression as an AST against an
allowlist before running it, executes it with builtins stripped, and presents
the result as exploratory rather than as a defined metric.

Every number still comes from pandas. That part does not change and is not
negotiable.

What changes is what is being trusted. In the metric lane, both the
computation and the interpretation are pinned: a registered metric decides
what "attainment" counts, and a human wrote that down. In the fallback lane
the computation is still deterministic, but the interpretation is
model-generated, so the answer carries the expression in full and a warning
stated in the strongest terms the interface has. A reader should never have to
guess which lane answered them, and the one that carries more risk is the one
that says so loudest.

Region and product line both stay refused ahead of both lanes, each with its
own reason computed from the data rather than quoted from a written string.

## User Stories

1. As a sales leader, I want a question the registry doesn't cover to be
   answered from the data anyway, so that an unregistered question isn't a
   dead end.
2. As a sales leader, I want an unmissable warning when an answer came from a
   generated query rather than a defined metric, so that I know to check it
   before I repeat it to anyone.
3. As a sales leader, I want the expression behind an exploratory answer shown
   without opening anything, so that the thing I can't otherwise check is the
   thing most in front of me.
4. As a sales leader, I want exploratory answers to carry no verified badge,
   so that the badge keeps meaning exactly one thing.
5. As a sales leader, I want region to keep refusing even though the fallback
   could compute it, so that a deliberate decision isn't quietly reversed by a
   new feature.
6. As a sales leader, I want product line to refuse with the attribution
   problem named, so that I understand a number was withheld on purpose rather
   than missing by accident.
7. As a sales leader, I want to be told when a question can't be answered from
   the columns that exist, so that I learn the boundary rather than receive a
   confident answer about data nobody has.
8. As a sales leader, I want the row count and the frame an exploratory answer
   read from, so that I can tell a Q1 answer from a Q2 one.
9. As an analyst, I want the generated expression to be reproducible by hand,
   so that I can paste it into a notebook and get the same number.
10. As an engineer, I want a generated expression validated before it runs, so
    that the safety of the lane doesn't depend on the model behaving.
11. As an engineer, I want a rejected expression to refuse rather than be
    repaired, so that the failure mode stays a visible no.
12. As an engineer, I want the fallback to read the same frames the metrics
    read, so that the two lanes can never disagree about what "open" means.
13. As an engineer, I want every fallback attempt logged with its question,
    expression, and outcome, so that V3 has something to promote from.
14. As an engineer, I want the registry consulted first, so that a question a
    metric covers is never answered by generated code.

## Implementation Decisions

### Lane precedence

Four steps, in order, and the first that applies wins:

1. Refused topics short-circuit, before any model call. Region does this
   today; product line joins it.
2. The router runs against the catalog. A registered metric that validates
   answers in the metric lane, unchanged from V1.
3. Otherwise the fallback lane attempts the question.
4. If the fallback declines or its expression fails validation, the system
   refuses with the catalog coverage hint, as V1 does now.

The registry is consulted first and always wins. A question a metric covers
must never be answered by generated code, because the metric encodes a
business definition a human agreed to and the generated expression does not.

Refused topics are checked ahead of everything for the reason region is today:
the one wrong move available to a model asked about a refused topic is
silently substituting a nearby column, and that substitution is invisible
downstream because the substituted value is a real one.

### Refused topics

Two topics refuse permanently, and they refuse for different reasons. Both
reasons are computed at load time rather than typed into a string, so neither
can go stale against the data.

**Region** refuses because two definitions of it disagree. The deal carries
one, the rep who owns the deal carries another, and they differ on 17 of 92
deals in the current snapshot. Unchanged from V1.

**Product line** refuses because attribution has never been agreed. The data
is clean, which is exactly why the refusal has to say something truthful
rather than imply a defect: there are no nulls in either snapshot, the value
set is identical across both, and all seven cross-snapshot changes belong to
IDs the reconciler already classifies as reused. The problem is that every
deal records exactly one product line, so any product-line total assigns that
deal's whole value to a single product. The refusal reports how many deals
carry exactly one product line, names the attribution question, and says the
number is withheld pending a decision rather than missing.

This distinction matters more than it looks. A refusal that implies bad data
where the data is fine is its own kind of dishonesty, and it would be caught
by the first analyst who checked.

Account-level questions were listed out of scope in V1 and are now answerable
through the fallback lane, since accounts carry no equivalent ambiguity.

### What the generator sees

Column names, dtypes, and the distinct values of low-cardinality columns, in
the same shape the router prompt already uses. It never receives a data row.
The generator is structurally incapable of leaking a figure into its output
because it was never shown one, which is the same guarantee the router rests
on and for the same reason.

It also receives the frames it may name and nothing about how they were built,
since the expression it writes is validated against the allowlist rather than
against its own understanding.

If a question needs a column that does not exist, the generator returns a
decline with a reason instead of an expression. Declining is cheap. An
expression over a column nobody has is a refusal one step later anyway, and a
plausible-looking substitution is worse than either.

### The sandbox

Recorded in ADR-0006. A single pandas expression, parsed with
`ast.parse(mode="eval")`, walked node by node against an allowlist, then
executed with `__builtins__` emptied and only the allowlisted frames bound.

Allowed: references to the named frames, subscripting, comparisons, boolean
and arithmetic operators, constants, lists and tuples, attribute access to
allowlisted method names, and calls to those methods only.

Rejected: imports, lambdas, comprehensions, assignments, walrus, `await`,
`yield`, f-strings with embedded calls, any attribute whose name begins with
an underscore, and any call to a name or method not on the list. The
underscore rule is what closes `__class__`, `__globals__`, and the rest of
that family in one line rather than by enumerating them.

The allowlist of methods is deliberately small and lives in one place. A
method nobody put on the list is a refusal, not a bug report.

Validation always runs before execution. A rejected expression refuses. It is
never repaired, never partially executed, and never retried with the offending
clause stripped, because a repaired query answers a question nobody asked.

Execution is additionally bounded: the result must be a DataFrame, a Series, or
a scalar, and a result larger than a row cap is truncated for display with the
full count reported.

### Frames the lane may name

`deals_q1`, `deals_q2`, `quotas`, and `reps`, bound to the same objects the
metrics use. Named per snapshot rather than as one frame, because a fallback
that silently blends the two snapshots would reintroduce the exact error the
reconciler exists to prevent. There is no combined frame and no way to ask for
one.

### Facts, narration, and the badge

The result is converted into Facts the same way a metric's is, so the narrator
still sees only computed values and the verifier still checks every numeric
token in the prose against them. The no-hallucinated-number guarantee is
unchanged in this lane.

What is not guaranteed is that the expression answered the question that was
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

Under the warning: the generated expression shown expanded and never behind a
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
expression, whether validation passed, whether execution succeeded, and the
row count. This is what V3's promote-to-metric path reads, and it is the
cheapest possible thing that makes V3 possible, so it ships now rather than
being retrofitted onto a lane that has already been answering questions.

The log is append-only and local. No question text leaves the machine.

### Models

The generator uses the router's model, `claude-sonnet-5`, from the same
configuration constant. Writing a correct pandas expression against a schema
is closer in kind to routing than to narrating, and a wrong expression is a
wrong answer, so it gets the stronger model.

## Testing Decisions

The primary seam stays `ask(question, data, client)`. Fallback answers are
asserted through it the same way metric answers are.

The validator is a deliberate second seam, tested directly, for the same
reason the reconciler's change log was in V1: it is the highest-risk code in
the system and getting it wrong reproduces a failure worse than the one the
project exists to prevent. Its tests are adversarial rather than illustrative
and include at minimum dunder traversal, import attempts, lambda and
comprehension bodies, calls to non-allowlisted methods, references to
unbound names, and attempts to reach a builtin.

Covered through the primary seam:

- A product-line question answers in the fallback lane with a table.
- A question a metric covers is answered by the metric lane, never the
  fallback, asserted by the lane marker.
- Region refuses and no generation is attempted.
- A question needing a column nobody has refuses rather than answering.
- An exploratory answer carries no verified-metric badge and does carry its
  expression.
- Prose in the fallback lane is still verified against facts, asserted by
  stubbing prose containing an unlisted figure and seeing it blocked.
- The two snapshots are never blended, asserted by the frames the lane exposes.
- Every fallback attempt appends exactly one log record, including refusals.

## Out of Scope

Promote-to-metric, which is V3 and is what the query log exists to feed.

Writes of any kind. Joins the metric lane doesn't already make available.
Multi-turn refinement of a generated expression. Charts over exploratory
results, since a chart implies a settled shape and these do not have one.

Region and product line, permanently, on the grounds in Refused topics above.
Both remain refusals in V2 even though the fallback lane could compute either
of them, which is the point: a lane that can answer anything is exactly the
lane most likely to answer something it shouldn't.

## Further Notes

### Planned for V3

A promote-to-metric path: a fallback query that keeps recurring in the log gets
turned into a registered metric, with the generated expression as the starting
point for the metric body and a human writing the definition text before it
ships. The point of V3 is that the human writes the definition, so the
promotion is a decision rather than a copy.

### Stack

No new dependencies. `ast` is standard library and the frames already exist.
`duckdb` and `sqlglot` are not adopted, per ADR-0006.

The vocabulary used throughout this spec is defined in `CONTEXT.md` at the
repo root.
