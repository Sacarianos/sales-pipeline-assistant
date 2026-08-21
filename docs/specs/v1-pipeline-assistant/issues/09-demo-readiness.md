# 09: Demo readiness

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** The whole thing runs as a demo for a skeptical audience. All
five acceptance cases pass end to end against the real models, the sidebar
suggests questions the system can actually answer, and the README makes the trust
argument in the form someone can read in two minutes.

The sidebar example questions come from the catalog rather than a hardcoded list,
same as the refusal message. A hardcoded example that drifts out of sync with the
registry is a demo failure waiting to happen, and wiring it to the catalog is
also part of proving the one-file extensibility claim.

The README covers why the language model never produces a number, how the two
model calls are fenced, what the verifier does when it catches something, and how
to add a metric by editing one file. That last part gets a worked example, since
showing the diff during a walkthrough is a stated goal and a diff that has to be
improvised on the day is not a diff worth showing.

**Blocked by:** 02, 03, 04, 05, 06, 07, 08

**Status:** ready-for-human

- [x] Enterprise tracking against quota this quarter answers correctly end to end
      with prose and a verified badge
- [x] Which reps are at risk of missing Q2 answers correctly end to end
- [x] How Q2 compares to the same point in Q1 answers correctly end to end
- [x] The West region question refuses with its computed conflict count
- [x] The Slack sentiment question refuses with the catalog coverage list
- [x] Sidebar example questions are read from the catalog
- [x] The README explains the trust argument, the architecture, and the two
      fenced model calls
- [x] The README carries a worked example of adding a metric in one file
- [x] The router uses `claude-sonnet-5` and the narrator uses
      `claude-haiku-4-5-20251001`, both from a configuration constant
- [x] The app runs from a clean checkout with documented setup steps

**Implementation notes:** all five acceptance questions were run by hand
against the real `claude-sonnet-5` router and `claude-haiku-4-5-20251001`
narrator (not stubbed), through both the primary seam and the Streamlit UI
itself. Four answered with narrator prose and a verified badge; the risk
question answered correctly but with the template sentence, because the
narrator wrote "best-case coverage above 100%" and the verifier correctly
blocked it, since 100 is the risk threshold, not a fact it was ever handed.
That's the designed fallback firing on a true statement, not a defect, and
the README calls it out as a concrete illustration of the trust argument
rather than papering over it. The chat input's placeholder question now
reads `catalog.examples()[0]` instead of a literal string, so the one other
hardcoded example question in `app.py` can't drift out of sync with the
registry either, matching the sidebar's existing catalog wiring. 10 tests in
`tests/test_demo_readiness.py`, 101 passing overall. Reviewed via
`/code-review` on both axes; findings were shared with issue 08 (see its
implementation notes) and nothing 09-specific was raised.
