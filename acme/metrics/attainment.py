"""Attainment: closed-won revenue against quota for a period.

Everything this metric needs is in this file — its computation, its registration,
the groupings it answers at, the intent fields it reads, the definition keys it
rests on, and the example questions the sidebar and the router prompt show. The
definition text itself lives in `acme.definitions`, which is shared
vocabulary rather than metric code.

Issue 02 adds segment, rep, and manager to the overall grouping issue 01 shipped.
A grouping other than overall is answered by scoping every figure — closed-won,
quota, open pipeline, best case, win rate — to whichever of segment, rep, or
manager the intent named, rather than by producing a breakdown across every
value at once. Best-case and win-rate-weighted are computed here as their own
facts and never folded into `attainment_pct`, since that folding is exactly the
silent redefinition the parent spec calls out.

Issue 06 adds the restated figure for Q1 questions. A Q1 question reads the
Q1 snapshot as reported, the same as it always has, and additionally scopes
the Q2 snapshot to deals whose close date still falls in Q1 to compute what
that same period looks like now that reopenings, unwinds, and ID reuse have
come to light. The restated facts only exist when the answer is about Q1 —
a Q2 question never gets them, since there is nothing to restate yet.
"""

from __future__ import annotations

import pandas as pd

from ..domain import Fact, Intent, Result, Unit
from ..loading import quota_total
from ..periods import bounds, day_of_quarter, days_in_quarter, snapshot_for, year_of
from ..registry import MetricRequest, metric


@metric(
    name="attainment",
    description=(
        "Closed-won revenue for a period against the quota for that period, as a "
        "percentage. Open pipeline is excluded from the percentage and reported "
        "beside it. Answers overall or scoped to one segment, rep, or manager."
    ),
    groupings=("overall", "segment", "rep", "manager"),
    intent_fields=("period", "grouping", "segment", "rep", "manager"),
    definition_keys=(
        "attainment",
        "period_membership",
        "open_deal",
        "quota_source",
        "best_case",
        "win_rate_weighted",
        "restated",
    ),
    examples=(
        "how are we tracking this quarter",
        "what is our attainment against quota right now",
        "how is the Enterprise segment doing this quarter",
        "how is Marcus Rivera tracking against quota",
    ),
)
def attainment(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    snapshot = snapshot_for(period)
    start, end = bounds(period)

    deals = request.data.deals(snapshot)
    rows = deals[deals["period"] == period]
    rows = _scope(rows, intent).sort_values("close_date")

    won = rows[rows["is_won"]]
    lost = rows[rows["is_lost"]]
    opened = rows[rows["is_open"]]

    closed_won = float(won["deal_value"].sum())
    open_pipeline = float(opened["deal_value"].sum())
    closed_lost = float(lost["deal_value"].sum())
    best_case = closed_won + open_pipeline

    closed_total = closed_won + closed_lost
    win_rate_pct = closed_won / closed_total * 100 if closed_total else 0.0
    win_rate_weighted = closed_won + open_pipeline * (win_rate_pct / 100)

    quota = quota_total(
        request.data.quotas, period,
        segment=intent.segment, rep=intent.rep, manager=intent.manager,
    )
    percent = closed_won / quota * 100 if quota else 0.0

    # A Q1 question also reads the Q2 snapshot, scoped to the same period and
    # filters, to show what those Q1 deals look like now that reopenings,
    # unwinds, and ID reuse have come to light. Never computed for a Q2
    # question, since there is nothing to restate yet, and only surfaced when
    # it actually differs from as-reported — a segment or rep slice untouched
    # by reconciliation restates to the same figure, and the parent spec
    # shows restated "alongside" as-reported only when the two differ.
    restated_closed_won: float | None = None
    restated_percent: float | None = None
    if period == "Q1-2026":
        restated_rows = request.data.deals("Q2")
        restated_rows = restated_rows[restated_rows["period"] == period]
        restated_rows = _scope(restated_rows, intent)
        candidate = float(restated_rows[restated_rows["is_won"]]["deal_value"].sum())
        if abs(candidate - closed_won) >= 1:
            restated_closed_won = candidate
            restated_percent = restated_closed_won / quota * 100 if quota else 0.0

    facts = {
        "closed_won": Fact(closed_won, Unit.CURRENCY, "Closed-won revenue"),
        "quota": Fact(quota, Unit.CURRENCY, f"{period} quota"),
        "attainment_pct": Fact(percent, Unit.PERCENT, "Attainment against quota"),
        "open_pipeline": Fact(open_pipeline, Unit.CURRENCY, "Open pipeline in the period"),
        "best_case": Fact(
            best_case, Unit.CURRENCY, "Best case: closed-won plus open pipeline"
        ),
        "win_rate_pct": Fact(win_rate_pct, Unit.PERCENT, "Win rate by value"),
        "win_rate_weighted": Fact(
            win_rate_weighted, Unit.CURRENCY, "Win-rate-weighted pipeline"
        ),
        "won_deal_count": Fact(float(len(won)), Unit.COUNT, "Deals closed won"),
        "deal_count": Fact(float(len(rows)), Unit.COUNT, "Deals closing in the period"),
        "period_year": Fact(float(year_of(period)), Unit.DATE, "Year of the period"),
        "day_of_quarter": Fact(
            float(day_of_quarter(period, request.as_of)), Unit.COUNT, "Day of the quarter"
        ),
        "days_in_quarter": Fact(
            float(days_in_quarter(period)), Unit.COUNT, "Days in the quarter"
        ),
    }
    if restated_closed_won is not None:
        facts["restated_closed_won"] = Fact(
            restated_closed_won, Unit.CURRENCY,
            "Closed-won revenue restated from the Q2 snapshot",
        )
        facts["restated_attainment_pct"] = Fact(
            restated_percent, Unit.PERCENT,
            "Attainment against quota, restated from the Q2 snapshot",
        )

    table_row = {
        "period": period,
        "grouping": intent.grouping,
        "segment": intent.segment or "",
        "rep": intent.rep or "",
        "manager": intent.manager or "",
        "closed_won": closed_won,
        "quota": quota,
        "attainment_pct": round(percent, 1),
        "open_pipeline": open_pipeline,
        "best_case": best_case,
        "win_rate_weighted": win_rate_weighted,
        "won_deals": len(won),
        "deals": len(rows),
    }
    if restated_closed_won is not None:
        table_row["restated_closed_won"] = restated_closed_won
        table_row["restated_attainment_pct"] = round(restated_percent, 1)
    table = pd.DataFrame([table_row])

    filters = {
        "snapshot": f"{snapshot} snapshot",
        "period membership": f"close_date between {start} and {end}",
        "grouping": intent.grouping,
    }
    if intent.segment:
        filters["segment"] = intent.segment
    if intent.manager:
        filters["manager"] = intent.manager
    if intent.rep:
        filters["rep"] = intent.rep
    if not (intent.segment or intent.manager or intent.rep):
        filters["scope"] = "no rep, segment, or manager filter"

    template = (
        f"{period} attainment {_scope_phrase(intent)} is {percent:.1f} percent: "
        f"{closed_won:,.0f} closed-won against a {quota:,.0f} quota, from "
        f"{len(won)} won deals, with {open_pipeline:,.0f} still open."
    )
    definition_keys = (
        "attainment",
        "period_membership",
        "open_deal",
        "quota_source",
        "best_case",
        "win_rate_weighted",
    )
    if restated_closed_won is not None:
        template += (
            f" As reported leads; restated from the Q2 snapshot it is "
            f"{restated_closed_won:,.0f} closed-won, {restated_percent:.1f} "
            f"percent of quota."
        )
        definition_keys = definition_keys + ("restated",)

    return Result(
        facts=facts,
        table=table,
        source_rows=rows[SOURCE_COLUMNS].reset_index(drop=True),
        filters=filters,
        snapshot=snapshot,
        definition_keys=definition_keys,
        template=template,
    )


def _scope(rows: pd.DataFrame, intent: Intent) -> pd.DataFrame:
    """Narrow to whichever of segment, rep, or manager the intent named.

    Filter agreement is checked in validation before a metric ever runs, so a
    question naming more than one of these has already been confirmed to agree
    with the others rather than silently overriding one.
    """
    if intent.segment:
        rows = rows[rows["segment"] == intent.segment]
    if intent.manager:
        rows = rows[rows["manager"] == intent.manager]
    if intent.rep:
        rows = rows[rows["rep_name"] == intent.rep]
    return rows


def _scope_phrase(intent: Intent) -> str:
    if intent.rep:
        return f"for {intent.rep}"
    if intent.manager:
        return f"for the team under {intent.manager}"
    if intent.segment:
        return f"for the {intent.segment} segment"
    return "across the whole organization"


SOURCE_COLUMNS = [
    "deal_id",
    "account_name",
    "segment",
    "rep_name",
    "manager",
    "stage",
    "deal_value",
    "close_date",
    "period",
    "loss_reason",
]
