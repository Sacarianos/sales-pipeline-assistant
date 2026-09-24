---
title: Conversation memory
triage: ready-for-human
category: enhancement
---

# Conversation memory

## Problem Statement

Every question is answered as if it were the first. A sales leader who asks
how Enterprise is tracking and then asks "what about SMB?" gets a refusal or
a guess, because the router never saw the first question. Real analysis is a
chain of refinements, and a tool that makes every link a full sentence gets
used like a search box, not a colleague.

## Solution

Earlier turns reach the router and the exploratory generator as context, so
a follow-up can be read in light of what came before. The narrator stays
one-shot. Everything that makes an answer trustworthy today still holds for
a follow-up: the reading is complete and restated, every figure is computed
fresh, and refused topics are refused.

## Implementation Decisions

### Memory holds readings, never answers

For each earlier turn the models are given the question and how it was read:
the intent for a metric answer, or the query plan and its plain English
description for an exploratory one. Never the prose, the facts, the table,
or any figure an answer produced.

The router and the generator have never been shown a data figure, and that is
what makes their guarantee structural. An earlier answer is full of figures,
so passing it along would give a model a figure to carry forward into a
filter value or a restatement, and nothing downstream checks those against
data. A reading carries everything a follow-up needs, because a follow-up
changes what was asked, not what was answered.

### A follow-up resolves to a complete reading

The router still returns a full intent, never a partial one merged later.
"What about SMB?" after an Enterprise attainment question comes back as
attainment, segment SMB, the same period, with every field filled in.

The restatement says the question was read as a follow-up and what it
carried over: "Following on from your last question, reading this as
attainment for the SMB segment for Q2-2026." A wrong carry-over has to be as
visible as a wrong route, and the restatement is where a reader looks.

If it's unclear which earlier question a follow-up refers to, the router
marks it ambiguous and the question refuses, the same as an ambiguous name.

### An exploratory follow-up refines the previous plan

When the previous answer was exploratory, the generator gets its plan and
may return a refined copy of it. The answer then shows what changed, worked
out by comparing the two plans in code, like "Changed from your last query:
added segment is Enterprise." The reader sees the refinement as a difference,
not as a whole new query to reread.

### What doesn't change

- Refused topics are checked on the new question alone, before memory is
  consulted. "What about the West?" refuses as region.
- Lane precedence is the same. A follow-up to an exploratory answer can land
  in the metric lane, and the other way round.
- Every figure is computed fresh from the data for the new reading.
- The narrator sees only the current question, restatement, and facts.

### Window and lifetime

The last three turns are remembered. Memory lives in the browser session and
is never written to disk. A "New conversation" button clears it along with
the transcript.

The offline keyword router ignores memory. A follow-up asked offline is read
on its own, and the offline banner already tells the reader to check the
restatement.

### Query log and promotion

Log records say whether the question was a follow-up. A follow-up still
counts toward its plan's candidate in promotion, but it isn't suggested as an
example question, since "just for Enterprise" means nothing to the router on
its own.

## Testing Decisions

The seam stays `ask`, which gains the earlier turns as an argument. Tests
assert that a follow-up's context reaches the router and the generator, and
that no figure from an earlier answer does. The plan comparison is tested
directly.

The evals gain multi-turn cases: a question or two asked first, then the
follow-up, scored the same way as any other case. One case checks the
opposite failure, a new standalone question that must not inherit the
previous scope.

## Out of Scope

Memory across sessions. Pronouns that reach further back than three turns.
Letting the narrator refer to earlier answers.

## Notes

Built in `acme/conversation.py`, with `ask` taking the earlier turns as
`history`. The evals gained eight multi-turn cases, and their first runs
changed three decisions:

- The generator only sees earlier turns when the router reads the question
  as a follow-up. Shown them for every question, it filtered a standalone
  "why are we losing deals" to the Enterprise segment of the question before
  it, once in three runs.
- `unsupported_kind` gained `metric_limit`, for a question a metric covers at
  another grouping. The router had been asked to name the metric anyway and
  let validation refuse, but "risk by segment" means a breakdown, which the
  grouping rule reads as overall, and the model resolved that by marking it
  unsupported, which sent it to the exploratory lane. It now has its own kind,
  and the pipeline refuses it.
- A follow-up's restatement shows above the answer in the chat. The chat
  leaves a standalone restatement to the trace panel, which isn't enough
  when the thing to check is what got carried over.

The "New conversation" button sits in the sidebar. Beside the chat heading
it made the column taller than a 730-pixel window and pushed the chat input
below the fold, which also showed that the transcript's sizing rule matched
every layout wrapper in the column. That rule now targets the keyed
transcript alone.

Exploratory answers now list the matched rows under source rows, not the
result table, the same as metric answers.

Evals: 114 of 114 across three repeats, including 24 of 24 follow-up runs.
282 tests passing.
