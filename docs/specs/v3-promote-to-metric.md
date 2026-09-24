---
title: V3 promote a query plan to a metric
triage: ready-for-human
category: enhancement
---

# V3 promote a query plan to a metric

## Problem Statement

The exploratory lane answers what no metric covers, and every answer it
gives carries a red warning, because nobody has agreed that its query means
what the reader thinks it means. That warning is right for a one-off. It is
wrong for a question people ask every week. A leader who sees the same red
banner on the same loss-reason question each Monday learns to read past it,
and a warning people read past has stopped doing its job.

V2 records every exploratory attempt in the query log. Nothing reads it yet.

## Solution

A command-line path that reads the query log, groups the answered plans that
keep recurring, and turns one of them into a registered metric file under
`acme/metrics/`. Once the file exists, the question routes to the metric
lane like any other metric: verified badge, no red warning, and a definition
a person wrote.

The point is that a person writes the definition, so promotion is a decision
and never a copy. The tool refuses to write a metric whose description was
left empty or copied from the machine's own description of the plan.

## What a person decides

The promotion tool asks for exactly these, and refuses until each is given:

1. **A name.** A new snake_case name no registered metric already uses.
2. **The definition.** The metric's description, in the person's own words.
   It becomes the text the router prompt, the sidebar, and the refusal
   coverage list all read, so it is what "this metric" means from then on.
   It can't be empty, can't be the plan's generated description, and needs
   at least eight words, since a two-word label doesn't say what a metric
   counts.
3. **Groupings.** Which of segment, rep, and manager the metric answers at,
   on top of overall. Only groupings the plan's frame has a column for.
4. **Example questions.** At least one. The tool suggests the questions from
   the log that produced the plan.
5. **Definition keys.** Which existing definitions the answer rests on, like
   `period_membership` or `open_deal`. Each one becomes a definition flag on
   every answer, the same as for the hand-written metrics.

## What promotion changes on its own

Two things change between the exploratory plan and the metric, and the tool
states both before it writes anything.

**Period.** An exploratory plan read a whole snapshot unless it filtered on
`period`. A metric answers for the period the question asks about, so a
promoted plan over deals reads the deals closing in that period, from the
snapshot that owns it, the same period membership rule every metric uses. A
plan over quotas reads that period's quotas. A plan over reps has no period.
Any `period` filter in the logged plan is dropped, since the question now
supplies it.

**Scope.** An `eq` filter on segment, rep name, or manager in a logged plan
is lifted out and becomes a suggested grouping. "Enterprise loss reasons"
and "SMB loss reasons" are the same metric at the segment grouping, not two
metrics.

## Grouping the log

Only answered records count. Two plans are the same candidate when they
match after normalizing: the snapshot frame becomes plain `deals`, period
filters are dropped, scope filters are lifted, and defaults are filled in.
Candidates rank by how often they were asked. A candidate whose plan no
longer passes the checker, because a column was removed or withheld since it
was logged, is left out.

## The generated file

One module per metric, like every other metric. It holds the normalized plan
as a literal, the `@metric` registration with the person's answers, and a
three-line compute function that hands both to a shared runtime in
`acme/promoted.py`. The runtime builds the concrete plan for the asked
period and scope and runs it through the same checker and pandas as the
exploratory lane. Nothing the model wrote executes here either. The plan was
data when it was logged, and it's data in the file.

Before writing, the tool runs the new metric for every period in the data,
at every grouping it claims, and refuses if any of those fail.

A promoted metric reads validated intent values, not model output, so the
checker's rule that a category filter must name a value the column holds is
relaxed for scope filters. A rep with no deals in a period gets zero rows, not
a rejection.

## Testing Decisions

The primary seam stays `ask`. The end-to-end test promotes a logged plan into
a temporary file, loads it, and asserts the same question now answers in the
metric lane with the verified badge path. The promotion module is a second
seam, tested directly for candidate grouping and for each refusal.

## Out of Scope

Editing or retiring a promoted metric. It's an ordinary metric file once
written, so a person edits it like any other.

A UI for promotion. It's a deliberate, rare act by whoever maintains the
metric catalog, and a command line fits that better than a button next to
the chat.

Promoting a declined or rejected question. Those need a new column or a new
computation, which is a person's work, not a promotion.

## Notes

Built in `acme/promotion.py` for candidates, checks, and rendering,
`acme/promoted.py` for the runtime a promoted metric calls, and
`acme/promote.py` for the command line.

Two changes elsewhere came out of it. `QueryResult` now carries the rows the
filters matched, so a promoted metric's answer shows real source rows. And
the `small_sample` and `changed_deals` flags now skip answers whose source
rows aren't deals. A promoted metric over quotas crashed `changed_deals` with
a KeyError before that, and `small_sample` would have called one quota row
"1 deal". Flags on every existing metric question are unchanged.

Checked end to end in the running app with a scripted client: two loss-reason
questions answered in the exploratory lane and landed in the log, `list`
grouped them into one candidate, `promote` refused a two-word definition and
then wrote the file, and after a restart the same question answered in the
metric lane with the verified badge, the definition in the sidebar, and the
period-membership definition flag. The count dropped from 9 to 1, which is
the period change working: the exploratory plan counted every closed-lost
deal in the Q2 snapshot, and the metric counts the ones closing in Q2. The
demo metric was deleted afterwards, since it came from scripted answers.
229 passing.

