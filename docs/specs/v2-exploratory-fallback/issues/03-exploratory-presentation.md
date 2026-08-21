# 03: Exploratory presentation

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** An exploratory answer nobody could mistake for a defined
metric, led by a warning nobody could read past.

The warning comes first, in red, above the answer rather than below it. It
says the answer did not come from a defined metric in the catalog, that a
model wrote the query, and that the figure should be checked before it is
repeated to anyone. This is the one place in the app where alarm is the right
register. Everywhere else the interface works to keep caveats legible without
making them frightening, because a leader alarmed by a partial-period notice
stops reading notices altogether. Here the risk is specific and real, so the
treatment matches it.

The distinction being drawn is narrow and worth stating precisely on screen.
The numbers in an exploratory answer are computed by pandas and checked by the
verifier exactly as a metric's are. What is not pinned is whether the query
answered the question that was asked, because a model wrote it. So the
treatment marks the interpretation as unverified, not the arithmetic, and the
warning should say that rather than implying the arithmetic is suspect.

The generated expression renders expanded and never behind a click. It is the
one thing a reader cannot otherwise check, which makes it the thing that
belongs most in front of them.

The badge differs from the metric lane's. A verified metric answer says how
many figures were checked against computed values. An exploratory answer says
the figures were computed and checked but the query was model-written.

The four detail sections stay as they are. Flags still run, because a partial
period and a stale close date are properties of the data rather than of the
lane that read it.

**Blocked by:** 02

**Status:** ready-for-human

- [x] A red warning renders above the answer, not below it
- [x] The warning says the answer came from a generated query rather than a
      defined metric in the catalog, and to check it before repeating it
- [x] The warning marks the interpretation as unverified without implying the
      arithmetic is suspect
- [x] The warning is legible in both light and dark themes
- [x] An exploratory answer is visually distinct from a metric answer
- [x] The generated expression renders expanded, not behind a click
- [x] An exploratory answer carries no verified-metric badge
- [x] The badge says the figures were checked and the query was model-written
- [x] The row count and the frame that was read are both shown
- [x] Flags still run and render on an exploratory answer
- [x] The four detail sections render as they do for a metric answer
- [x] A truncated result says so and reports the full row count

**Implementation notes:** The warning uses `st.error`, which is themed by
Streamlit itself rather than by anything this app paints, so "legible in
both light and dark themes" comes for free. The generated expression renders
via `st.code` directly under the warning in the chat message, never behind
an expander - the same message bubble it's in has no click anywhere in its
path. A red `.exploratory-pill` badge above the warning gives the answer a
second, glanceable signal of visual distinctness beyond the warning color
itself.

The real gap this issue closed: `fallback.attempt()` (issue 02) never called
`flags.evaluate()` at all, so an exploratory answer carried zero flags
regardless of what the underlying snapshot's caveats were - not merely
unpolished, silently wrong once flags were expected to "still run" per this
issue. Wiring the existing `evaluate(intent, result, data)` straight through
turned out to be the wrong move on inspection: two of its nine rules
(`small_sample`, `changed_deals`) read `result.source_rows` as if it were the
metric's own filtered deal rows, but a fallback answer's result can be an
arbitrary aggregate (a `value_counts()` table has no "5 deals" to be a small
sample of). Feeding the whole snapshot in as a stand-in for `source_rows` to
dodge the small-sample false positive was tried first and reverted after a
live run showed `changed_deals` firing with 54 of the snapshot's ~90 deals
listed as chips under an unrelated loss-reason answer - technically true,
practically noise, and a regression from not having the flag at all. The
fix is `flags.evaluate_for_snapshot(period, snapshot, data)`, a second,
narrower entry point that runs only the four rules that are properties of a
snapshot on its own - `partial_period`, `stale_close_date`, `missing_field`,
`unknown_stage` - which is exactly the set the parent spec's own examples
name. `Answered.snapshot` also now gets set to whichever deals frame the
expression named (was hardcoded to `""`), which is what makes the Trace
panel's existing "Snapshot answering" caption correct for this lane instead
of blank.

Two findings from `/code-review` (Standards + Spec, both axes) were fixed
in response: the warning copy originally said figures were "verified
against the prose," backwards from how the verifier actually works (prose
is checked against figures, never the reverse) - a real error in the one
paragraph this issue asked to be worded precisely. The Q1/Q2-to-period
mapping was also duplicated as two parallel string ternaries in
`fallback.py` where `periods.py` already owns that correspondence in the
other direction (`snapshot_for`); `period_for_snapshot` closes the missing
inverse instead. A duplicated "model output blocked" caption string and a
duplicated rule-running comprehension in `flags.py` were also extracted.
The pill and the `Result.source_rows`-vs-whole-snapshot design tradeoff were
flagged as judgement calls, not fixed, since the pill directly serves the
visual-distinctness checklist item and the snapshot-scoped flags are the
correct semantics.

6 tests in `tests/test_exploratory_presentation.py`, 164 passing overall.
The presentation checklist items with no Streamlit test harness in this repo
(warning ordering, no-expander, badge gating) are asserted against `app.py`'s
own source text, the same precedent `test_demo_readiness.py` set for the
sidebar wiring. Verified live against the real API and both themes in the
browser preview; the `changed_deals`-on-the-whole-snapshot regression above
was caught this way; a `git diff`-based text check couldn't have surfaced it.
