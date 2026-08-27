# Compromises and tradeoffs

Every deliberate cut, judgment call, and known limitation in the V1 submission,
against two things: the assignment brief (`FDE_TakeHome_Acme.pdf`) and the
V1 plan (`docs/specs/v1-pipeline-assistant.md`). Grouped so pieces of this can
be lifted directly into the final report — particularly the "what you cut"
walkthrough and the "where does it still fall short" answer the brief asks
for by name.

## 1. Scope cut on purpose, stated in the plan before any code was written

From the V1 spec's Out of Scope section. These aren't things that didn't get
finished — they're things the plan explicitly decided not to build, each with
a reason.

- **Region questions refuse.** The deal's own `region` column and the region
  of the rep who owns it disagree on 17 of 92 deals. Answering would mean
  picking one definition silently. The refusal computes that count at load
  time rather than quoting a written string, so it can't go stale.
- **Account-level questions refuse.**
- **Forecasts and anything forward-looking refuse.**
- **Any period outside Q1-2026 and Q2-2026 refuses.**
- **Multi-turn follow-ups aren't supported.** Every question is answered
  independently; there's no conversation memory.
- **Authentication and write-back are absent entirely.** This is a read-only
  reporting surface with no login.
- **Rep-level comparison, and segment/manager-level risk, are out of
  scope**, per the grouping matrix (comparison answers overall/segment only;
  risk answers overall/rep only). A segment- or manager-level risk number
  would be a sum of individual best-cases against a summed quota, which
  hides the individual shortfall the metric exists to surface — cutting
  this wasn't just time-saving, it would have been a worse metric.

## 2. Business judgment calls the team made, not Acme policy

These are places the tool takes a stance a client stakeholder could
reasonably push back on. Each is disclosed on screen every time it's
relevant, but they're worth naming as compromises because they're exactly
the kind of quiet redefinition the brief's trust framing warns about if left
undisclosed.

- **The risk threshold (100% best-case coverage) is invented for this
  analysis, not a Acme standard.** A pace-based alternative was
  considered and rejected — at day 32 of a 91-day quarter, most reps have
  closed nothing yet, so pace would flag nearly everyone and tell a leader
  nothing actionable. Every risk answer states this threshold is the
  system's own choice.
- **The small-sample warning threshold (5 deals) is arbitrary.** Below it, a
  headline number gets flagged as resting on too few data points to read as
  a trend. Five is a judgment call, not a statistical derivation.
- **The "same day of quarter" comparison methodology is a design decision,
  not a given.** Comparing Q2 to Q1 by calendar date would compare a third
  of one quarter to the whole of another; matching by day-count avoids that,
  but it's still a modeling choice about what "fair comparison" means.
- **Period membership is close-date-only.** A deal belongs to the quarter
  its close date falls in, regardless of open/closed status or any other
  date field. This is the only rule the data actually supports (open deals
  in one snapshot carry the other quarter's close date), but it's still one
  rule chosen over alternatives that could exist in a real CRM.
- **"Open" is defined as the complement of Closed Won/Closed Lost**, not a
  maintained whitelist of open-stage names. Deliberate — the two snapshots
  use different open-stage vocabularies, and a whitelist someone forgets to
  update would silently drop deals with no flag. The tradeoff: Closed Won
  and Closed Lost are the only two stage names the system hardcodes anywhere,
  so if either is ever renamed, the complement logic breaks in a way an
  unknown-stage flag would not currently catch for those two specifically.

## 3. Architectural tradeoffs, recorded as ADRs

Each of these picked one approach over a real alternative, for a stated
reason. Full text in `docs/adr/`.

- **ADR-0001, ID reuse detection:** ID reuse is detected generically (both
  `account_name` and `created_date` change) rather than hardcoding the 13
  affected IDs. Costs more code; the alternative silently breaks on next
  quarter's snapshot.
- **ADR-0002, the Fact value object:** every number carries a unit and a
  label rather than living in a bare `dict[str, float]`. The alternative
  (a second, unchecked labels channel) would have given the model a place
  to introduce a number the verifier never checks — rejected specifically
  because it would have undermined the trust guarantee, not because it was
  more code.
- **ADR-0003, no pattern-based verifier exemptions:** numbers like the
  period year or day-of-quarter are supplied as real Facts rather than
  regex-exempted from verification. The cost is more Facts to maintain; the
  benefit is the verifier's rule has zero carve-outs to defend to a
  skeptical executive.
- **ADR-0004, offline router visibility:** when the online router is
  unreachable, the app falls back to a weaker keyword matcher rather than
  crashing — a real capability regression, made visible with its own banner
  rather than hidden. The offline router is allowed to refuse rather than
  guess when keyword matching is ambiguous.
- **ADR-0005, default period resolution:** a question that doesn't name a
  quarter defaults to the one containing today's pinned date, rather than
  refusing outright. This is an explicit exception to the tool's own
  "refuse rather than guess" philosophy, justified because forcing a
  quarter name onto every question would make the tool more annoying than
  the dashboards it replaces — and the default is always stated out loud in
  the restatement, so a wrong guess is as visible as a wrong metric would be.
- **No orchestration framework (LangChain/LangGraph explicitly rejected).**
  Two single-shot model calls with no agent loop and no cross-turn state
  don't need one, and every layer between the question and the pandas call
  is a layer that has to survive being explained to a skeptical executive.
  The cost: less flexibility if the system ever needs multi-step tool use.
- **Router and narrator use different models on purpose** — `claude-sonnet-5`
  for routing, `claude-haiku-4-5` for narration — and neither uses a
  frontier model (Opus). Explicit tradeoff: frontier models don't
  meaningfully outperform on constrained extraction, and the extra latency
  costs more in a live demo than the accuracy buys back.

## 4. A structural limitation found after the fact, not designed around

Discovered while answering "could you just add a Q3 folder" — the honest
answer is no, and not because of one missing config line.

- **The system is hardcoded to exactly two quarters in several places that
  don't generalize from `QUARTERS`/`PERIODS` the way the rest of the
  routing and validation layer does.** `periods.snapshot_for()` is a binary
  `if period == "Q1-2026" else "Q2"` — a third period would silently
  resolve to the Q2 snapshot rather than erroring, which is the most
  dangerous shape of bug this project's whole design otherwise avoids
  (wrong answer, verified badge, no visible failure). `config.SNAPSHOT_DIRS`
  is a fixed two-entry dict rather than a directory scan, so a new folder is
  silently never read at all. `QUOTA_COLUMNS` only knows two wide-format
  column names, so a third quota column would be silently dropped rather
  than flagged. The reconciler and divergence decomposition are pairwise by
  construction (`reconcile(snapshots["Q1"], snapshots["Q2"])`), which isn't
  a bug so much as an unanswered design question — reconciling a third
  snapshot needs a decision about what it reconciles against, and the code
  has no opinion because V1 never needed one.
- This wasn't a time-boxing cut — V1 only ever needed two quarters, so
  building N-quarter generality would have been speculative generality
  against a spec that named exactly Q1 and Q2. Worth naming anyway, because
  "add a quarter" is the single most likely extension request this tool
  will get.

## 5. Testing and process compromises

- **The automated test suite runs entirely against stubbed model clients**,
  not the real API — deterministic and free to run, but it means CI never
  actually exercises real router or narrator behavior. Live-API correctness
  was checked by hand at key points (all three of the brief's required
  example questions, the risk metric's threshold-blocking behavior, the
  comparison metric's day-of-quarter resolution) but that verification
  isn't part of the repeatable suite and would need to be re-run manually
  after any prompt change.
- **One place the implementation deliberately diverged from its own written
  issue spec.** The reconciler issue's checklist said one deal reopens
  between Q1 and Q2; independently verified against the CSVs, three
  non-reused deals (OPP-010, OPP-032, OPP-054) all satisfy the project's own
  definition of `reopened` with nothing distinguishing any one of them as
  special. Matching the written "one" would have meant hardcoding two of the
  three out via an ID exception list — exactly what the ID-reuse ADR exists
  to prevent elsewhere in the same module. Shipped the generically-computed
  value (three) instead of the spec's number, and documented why. Worth
  including in the report as evidence the team caught and corrected its own
  planning error rather than building to a wrong number because it was
  written down.
- **Product line refused, then didn't, after the reasoning was checked out
  loud.** It was cut from V1 alongside region on the same instinct: two
  things that sound like data-ambiguity problems. Pressed on it directly,
  the reasoning didn't survive contact: region refuses because two
  definitions of it actively disagree in the data, 17 of 92 deals, a
  measured contradiction. Product line has no second source to disagree
  with at all, just one clean tag per deal, no nulls, identical values
  across both snapshots. The "might be a bundled deal" story used to
  justify the refusal wasn't something found in the data; it was an
  assumption about how enterprise software is typically sold, presented
  with more confidence than it had earned. Reversed the call: `product_mix`
  now computes the split and discloses the one real assumption (a bundle,
  if one exists, would have its whole value counted toward a single tag)
  as a flag rather than withholding the number over it. Worth including in
  the report for the same reason as the reconciler item above, and because
  it's a clean example of the difference between a refusal earned by the
  data and a refusal that sounded like it was.
- **Every issue went through a two-axis code review (does it match this
  repo's own conventions; does it match the spec) before being marked
  done**, and every review that found something resulted in a fix before
  commit — nothing was accepted as "good enough for a demo." This is a time
  cost against the brief's 1-2 hour estimate, spent deliberately, since the
  brief's actual bar is trust, not speed.

## 6. Where the trust guarantee itself has a seam

Distinct from "missing features" above — these are gaps *inside* what was
built, present even when everything works as designed. This is the direct
answer to the brief's third deliverable ("where does it still fall short").

- **The verifier checks that narrated numbers match computed Facts. It does
  not check that the router picked the right metric, grouping, or filter.**
  A clean misroute — right shape of answer, wrong question — would compute
  correctly, narrate correctly, and verify cleanly, because every number in
  it would be real. The one-sentence restatement rendered inside every
  answer is the only defense against this, and it only works if a human
  actually reads it before repeating the number in a meeting.
- **Narration is non-deterministic, so the same question doesn't look the
  same twice.** Observed live, repeatedly: one run of a risk question has
  the narrator correctly cite each rep's figure and verify; another run of
  the identical question has it write "best-case coverage above 100%" — a
  true statement, but 100 was never handed over as a Fact — and get
  correctly blocked to the deterministic template. Never wrong, but a
  leader asking the same question twice can get a narrated paragraph once
  and a flatter template sentence the next time, with no visible reason why
  unless they understand the verifier.
- **Data-quality flags are an enumerated rule list, not a general anomaly
  detector.** The system catches exactly the problems someone thought to
  write a rule for (stale close dates, missing loss reasons, unknown
  stages, snapshot divergence). A data problem outside that list — a
  category nobody anticipated — produces no flag at all, and the interface
  gives no signal that its flag coverage is partial.
- **The offline keyword router is a materially weaker fallback**, not an
  equivalent. It still refuses rather than guesses on ambiguous input, and
  it's clearly banner-flagged when active, but it will misroute more often
  than the LLM router during any stretch when the API is unreachable.
- **Verification is numeric, not semantic.** The verifier confirms every
  digit in the prose traces to a Fact. It has no opinion on whether the
  surrounding sentence characterizes those digits fairly — nothing would
  catch a narrator describing a 4.5% attainment figure in an upbeat tone,
  as long as it didn't invent or miscalculate a number while doing it.

## 7. What's explicitly not a V1 compromise

For completeness, two things worth distinguishing from the list above so
they don't get conflated with it in the report: a second branch
(`v2-exploratory-fallback`) exists with an AST-sandboxed pandas fallback lane
for questions outside the registered metrics. It originally predated the
product-line reversal in section 5 and refused product line on the original
attribution reasoning. Main has since been merged into it and that refusal
removed: the refused-topic entry, the catalog reason method it called, and
the load-time count it quoted are gone, and the tests that asserted the
refusal now assert product line answers in the metric lane. The two are
consistent. The branch is not part of the V1 submission
and was built separately, as a demonstration of where the "one file per
metric" architecture goes next — not a cut made under pressure, and not
something the V1 artifact depends on or claims to include.
