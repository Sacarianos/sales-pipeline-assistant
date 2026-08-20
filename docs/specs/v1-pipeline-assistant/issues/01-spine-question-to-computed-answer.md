# 01: Spine, a question in and a computed number on screen

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader types "how are we tracking this quarter" into
a Streamlit chat box and gets back a direct answer with the figures behind it,
the deal rows that produced them, the filter that selected those rows, and the
structured intent that was read from the question. No language model is involved
anywhere in this ticket. The answer sentence is the deterministic template.

This is the tracer bullet through every layer. Everything else in this feature
hangs off the contracts it establishes, so the shapes matter more here than the
coverage does.

Load time reads both snapshots and the quota source, parses dates, normalizes
stage strings, melts quotas to one row per rep per period, and joins rep
attributes onto deals. `data/Q2/reps.csv` is the quota source for both quarters.
The as-of date is a configuration constant pinned to 2026-05-02 and is never
derived from the current date.

Query time runs a straight line: route, validate, compute, flag, render. One
early exit for a refusal. No orchestration framework.

The right-hand panel has four stacked sections, all visible without clicking:
the computed figures, the flags, the source rows with their filter and row count,
and a trace showing the intent and which snapshot answered. The restatement
renders inside the answer itself rather than in the trace, because it is the only
backstop against a silent misroute and a human has to see it without opening
anything.

Attainment at the overall grouping is the one metric. It is registered through
the decorator so that the registry and catalog exist from the start, since
retrofitting them later would mean rebuilding the router prompt, the validator,
and the refusal message against a moving target.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

- [x] Asking about the current quarter with no metric named returns 518,000
      closed against a 6,200,000 quota at 8.4 percent
- [x] `Fact` carries a value, a unit of currency, percent, count, or date, and a
      human label; `Result` carries facts, table, source rows, filters, snapshot,
      definition keys, and a template sentence
- [x] A deal belongs to the quarter its close date falls in, for open and closed
      deals alike; no other date field determines period
- [x] Open is computed as the complement of `Closed Won` and `Closed Lost`, not
      from a list of open-stage names
- [x] Adding a metric requires editing exactly one file, demonstrated by the
      registered attainment metric
- [x] The catalog is built by walking the registry plus the loaded data, and
      carries metrics, groupings, segments, reps, managers, periods, and the
      as-of date
- [x] The offline keyword router produces a valid intent including a templated
      restatement
- [x] The flags panel renders the partial-period rule reading day 32 of 91
      through 2026-05-02, and the plain-English attainment definition
- [x] The four right-hand panel sections all render without any click
- [x] The restatement appears inside the answer, not in the trace panel
- [x] Q1 quota totals 5,920,000 and Q2 totals 6,200,000 from the melted quota
      table

**Implementation notes:** `acme/` package plus `app.py` (Streamlit). Primary
seam is `acme.pipeline.ask(question, data, client)`. 13 tests in
`tests/test_spine.py`, all passing. Verified live in-browser for both the
answered and refused paths. Issue 02 widens attainment's `groupings` beyond
`overall`; issue 03 puts the Anthropic tool-use router in front of the
offline keyword one already here.
