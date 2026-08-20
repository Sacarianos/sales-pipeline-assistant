"""Attainment: closed-won revenue against quota for a period.

Everything this metric needs is in this file — its computation, its registration,
the groupings it answers at, the intent fields it reads, the definition keys it
rests on, and the example questions the sidebar and the router prompt show. The
definition text itself lives in `acme.definitions`, which is shared
vocabulary rather than metric code.

Issue 01 ships the overall grouping. Segment, rep, and manager arrive in issue
02 by extending the `groupings` tuple and the filter block below.
"""

from __future__ import annotations

import pandas as pd

from ..domain import Fact, Result, Unit
from ..loading import quota_total
from ..periods import bounds, day_of_quarter, days_in_quarter, snapshot_for, year_of
from ..registry import MetricRequest, metric


@metric(
    name="attainment",
    description=(
        "Closed-won revenue for a period against the quota for that period, as a "
        "percentage. Open pipeline is excluded from the percentage and reported "
        "beside it."
    ),
    groupings=("overall",),
    intent_fields=("period", "grouping"),
    definition_keys=("attainment", "period_membership", "open_deal", "quota_source"),
    examples=(
        "how are we tracking this quarter",
        "what is our attainment against quota right now",
        "how much have we closed in Q2",
    ),
)
def attainment(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    snapshot = snapshot_for(period)
    start, end = bounds(period)

    deals = request.data.deals(snapshot)
    rows = deals[deals["period"] == period].sort_values("close_date")

    won = rows[rows["is_won"]]
    opened = rows[rows["is_open"]]

    closed_won = float(won["deal_value"].sum())
    open_pipeline = float(opened["deal_value"].sum())
    quota = quota_total(request.data.quotas, period)
    percent = closed_won / quota * 100 if quota else 0.0

    facts = {
        "closed_won": Fact(closed_won, Unit.CURRENCY, "Closed-won revenue"),
        "quota": Fact(quota, Unit.CURRENCY, f"{period} quota"),
        "attainment_pct": Fact(percent, Unit.PERCENT, "Attainment against quota"),
        "open_pipeline": Fact(open_pipeline, Unit.CURRENCY, "Open pipeline in the period"),
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

    table = pd.DataFrame(
        [
            {
                "period": period,
                "grouping": "overall",
                "closed_won": closed_won,
                "quota": quota,
                "attainment_pct": round(percent, 1),
                "open_pipeline": open_pipeline,
                "won_deals": len(won),
                "deals": len(rows),
            }
        ]
    )

    filters = {
        "snapshot": f"{snapshot} snapshot",
        "period membership": f"close_date between {start} and {end}",
        "grouping": "overall, no rep, segment, or manager filter",
    }

    template = (
        f"{period} attainment across the whole organization is "
        f"{percent:.1f} percent: {closed_won:,.0f} closed-won against a "
        f"{quota:,.0f} quota, from {len(won)} won deals, with "
        f"{open_pipeline:,.0f} still open."
    )

    return Result(
        facts=facts,
        table=table,
        source_rows=rows[SOURCE_COLUMNS].reset_index(drop=True),
        filters=filters,
        snapshot=snapshot,
        definition_keys=("attainment", "period_membership", "open_deal", "quota_source"),
        template=template,
    )


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
]
