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

**Best-case coverage**:
Closed-won revenue plus open pipeline, compared against quota, both sides
filtered to the same period by period membership. The ceiling a rep could
still reach this quarter, not a probability-weighted forecast and not a
count of every open deal a rep has regardless of when it's slated to close.
_Avoid_: pipeline coverage, forecast

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
