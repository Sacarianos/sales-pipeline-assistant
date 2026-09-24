# Acme Pipeline Assistant

Domain glossary for the Streamlit pipeline-reporting assistant. Built for a sales
leader who needs every number traced back to a deterministic computation, after
a previous AI reporting tool hallucinated figures.

## Language

**Snapshot**:
One of the two point-in-time exports of `deals.csv` — Q1 (frozen at Q1 close) or
Q2 (current as of the as-of date). The two snapshots describe an overlapping
deal population that does not agree on what happened in Q1.
_Avoid_: file, dataset, export

**As-reported**:
A Q1 figure computed from the Q1 snapshot — what the business believed at the
time the quarter closed.
_Avoid_: original, headline

**Restated**:
The same Q1 figure recomputed from the Q2 snapshot, reflecting what the Q1
deals now look like after reopenings, unwinds, and ID reuse came to light.
_Avoid_: revised, corrected, updated

**Period membership**:
A deal belongs to the quarter its `close_date` falls in, whether the deal is
open or closed. No other date field determines period.
_Avoid_: booking date, created-date quarter

**Open (deal)**:
Any deal whose stage is not `Closed Won` or `Closed Lost`. Determined by
exclusion, not a maintained list of open-stage names, since the two snapshots
use different open-stage vocabularies.
_Avoid_: pipeline stage, active deal

**Region**:
Two disagreeing definitions exist in this data: the region recorded on the
deal itself, and the home region of the rep who owns it. They differ on 17 of
92 deals in the current snapshot, a count computed at load time rather than
written by hand. Region questions refuse for this reason rather than picking
one definition silently; segment carries no equivalent ambiguity.
_Avoid_: territory, area

**Product line**:
One of three values recorded on every deal. Unlike region, this is not two
definitions disagreeing: the column is clean, no nulls, an identical value
set across both snapshots. The `product_mix` metric reports closed-won and
open pipeline split by product line, with no quota comparison, since quotas
in this data are recorded per rep with no product breakdown to divide by.
The one real assumption is that each deal carries exactly one product-line
tag, so a bundled deal, if one exists, would have its whole value counted
toward a single product line. Nothing in this data confirms whether that
happens; the `product_line_attribution` flag says so on every answer rather
than the number being withheld over it.
_Avoid_: product, SKU

**Best case**:
Closed-won revenue plus open pipeline for a period, both sides filtered to
the same period by period membership. The ceiling that scope could still
reach, not a probability-weighted forecast. Reported as its own currency
Fact alongside attainment, never folded into it. Divided by quota, this is
best-case coverage.
_Avoid_: pipeline coverage, forecast

**Best-case coverage**:
Best case (above) compared against quota, per rep. The ceiling a rep could
still reach this quarter, not a count of every open deal a rep has
regardless of when it's slated to close. Anyone below 100 percent cannot
make quota even if every open deal they have closes.
_Avoid_: pace, on-pace

**Win-rate-weighted pipeline**:
Closed-won revenue plus open pipeline scaled by the period's win rate by
value — closed-won divided by all closed revenue, won and lost — rather
than assuming every open deal closes. A second, more conservative estimate
alongside best case, reported as its own Fact and never folded into
attainment.
_Avoid_: weighted forecast, expected pipeline

**ID reuse**:
A `deal_id` that refers to two different deals across snapshots — detected
when both `account_name` and `created_date` change for the same ID. Distinct
from a deal that was legitimately `reopened` or that `drifted` on an
attribute, and must never be reported as `unwon`.
_Avoid_: recycled deal, duplicate

**Fact**:
A single named, computed value with a unit and a human label, handed to the
narrator and checked by the verifier. The only channel through which a number
reaches prose. This includes derived numbers: a gap, delta, or margin stated
in prose ("short by 484,000") must be precomputed as its own Fact, never left
for the narrator to subtract from two other Facts — the model is forbidden
from arithmetic, not just from inventing figures outright.
_Avoid_: metric value, figure (when referring to the code-level object)

**Verified figure**:
A numeric token in narrator prose that matches a Fact's value, or an honest
rounding of it, within tolerance.
_Avoid_: validated number

**Query plan**:
What the exploratory fallback lane asks a model for when no registered metric
covers a question: one frame, filters, grouping, one aggregate, sort, and
limit. Checked against the frame schemas and run by code written by hand, so
nothing the model writes executes. Shown to the reader as a plain English
sentence and to an analyst as the equivalent pandas.
_Avoid_: generated query, expression, SQL

**Withheld column**:
A column a refused topic rests on, like region on the deal and region on the
rep. It is left out of every query plan's schema, and a plan naming one is
rejected, so the fallback lane can't answer a refused topic under another name.
_Avoid_: hidden field, blocked column

**Promoted metric**:
A registered metric made from a query plan that kept recurring in the query
log. A person names it, writes its definition, and picks its groupings. The
plan becomes data in the metric file, and each question runs it for the
asked period and scope, from the snapshot that owns that period.
_Avoid_: saved query, learned metric

## Reconciliation change types

One row per deal per outer join of `q1_snap` and `q2_snap`.

**new_in_q2**: exists only in the Q2 snapshot.
**unwon**: `Closed Won` in Q1, something else in Q2, same underlying deal.
**reopened**: `Closed Lost` in Q1, an open stage in Q2.
**drifted**: an attribute (region, value, etc.) differs between snapshots on
the same underlying deal.
**id_reused**: the `deal_id` points at two different deals across snapshots.
Takes precedence over `unwon` / `drifted` — those never fire on a reused ID.
**unchanged**: identical in both snapshots.
