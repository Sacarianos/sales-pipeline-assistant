"""Comparison: attainment for the current period against the same day of
quarter in an earlier one.

Matching by day of quarter rather than calendar date is the whole point.
Day 32 of Q2 is May 2; day 32 of Q1 is February 1. Comparing a third of one
quarter against the whole of another is the apples-to-oranges error this
metric exists to prevent.

The current side reads exactly like `attainment` does: closed-won revenue
for the period, no extra cutoff, since "now" already excludes anything that
hasn't closed yet. The comparison side additionally filters to deals closed
on or before the same-day-of-quarter cutoff date, because the earlier
quarter is fully elapsed and would otherwise show its whole total rather
than a same-point-in-time slice.

Each side is drawn from the snapshot that owns it and never blended: the
current side from the snapshot backing `intent.period`, the comparison side
from the snapshot backing `intent.comparison_period` as reported, never the
restated figure. The gap between the two percentages is precomputed as its
own fact, since the narrator is forbidden from arithmetic. The comparison
side's eventual (uncapped) total is precomputed too, so the backloading flag
in `acme.flags` can report how much of it had landed by the cutoff
without recomputing anything itself.
"""

from __future__ import annotations

import pandas as pd

from ..domain import Fact, Intent, Result, Unit
from ..loading import quota_total
from ..periods import bounds, date_for_day_of_quarter, day_of_quarter, snapshot_for, year_of
from ..registry import MetricRequest, metric

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


@metric(
    name="comparison",
    description=(
        "Attainment for the current period against the same day of quarter "
        "in an earlier one — matched by day count, not calendar date, so a "
        "third of a quarter is never measured against the whole of another. "
        "Each side is drawn from the snapshot that owns it and never "
        "blended. Answers overall or scoped to one segment."
    ),
    groupings=("overall", "segment"),
    intent_fields=("period", "comparison_period", "grouping", "segment"),
    definition_keys=(
        "comparison",
        "attainment",
        "period_membership",
        "quota_source",
    ),
    examples=(
        "how does Q2 attainment compare to the same point in Q1",
        "how do we compare to where we were at this point last quarter",
    ),
)
def comparison(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    comparison_period = intent.comparison_period
    assert comparison_period is not None  # validation guarantees this before compute runs

    snapshot = snapshot_for(period)
    comparison_snapshot = snapshot_for(comparison_period)
    start, end = bounds(period)
    comparison_start, comparison_end = bounds(comparison_period)

    # `day_of_quarter` already clamps a completed period to its own full
    # length once `as_of` is past its end, so a Q1 question reads as day 91
    # of 91 with no extra branching needed here.
    day = day_of_quarter(period, request.as_of)
    cutoff = date_for_day_of_quarter(comparison_period, day)

    current_rows = request.data.deals(snapshot)
    current_rows = current_rows[current_rows["period"] == period]
    current_rows = _scope(current_rows, intent)

    comparison_all_rows = request.data.deals(comparison_snapshot)
    comparison_all_rows = comparison_all_rows[comparison_all_rows["period"] == comparison_period]
    comparison_all_rows = _scope(comparison_all_rows, intent)
    comparison_rows = comparison_all_rows[comparison_all_rows["close_date"] <= cutoff]

    current_won = current_rows[current_rows["is_won"]]
    comparison_won = comparison_rows[comparison_rows["is_won"]]
    comparison_eventual_won = comparison_all_rows[comparison_all_rows["is_won"]]

    current_closed_won = float(current_won["deal_value"].sum())
    comparison_closed_won = float(comparison_won["deal_value"].sum())
    comparison_eventual_closed_won = float(comparison_eventual_won["deal_value"].sum())

    current_quota = quota_total(request.data.quotas, period, segment=intent.segment)
    comparison_quota = quota_total(
        request.data.quotas, comparison_period, segment=intent.segment
    )

    current_pct = current_closed_won / current_quota * 100 if current_quota else 0.0
    comparison_pct = (
        comparison_closed_won / comparison_quota * 100 if comparison_quota else 0.0
    )
    gap_pct = abs(comparison_pct - current_pct)

    facts = {
        "closed_won": Fact(current_closed_won, Unit.CURRENCY, f"{period} closed-won revenue"),
        "quota": Fact(current_quota, Unit.CURRENCY, f"{period} quota"),
        "attainment_pct": Fact(current_pct, Unit.PERCENT, f"{period} attainment against quota"),
        "deal_count": Fact(
            float(len(current_rows)), Unit.COUNT, f"Deals closing in {period}"
        ),
        "comparison_closed_won": Fact(
            comparison_closed_won, Unit.CURRENCY,
            f"{comparison_period} closed-won revenue by day {day}",
        ),
        "comparison_quota": Fact(
            comparison_quota, Unit.CURRENCY, f"{comparison_period} quota"
        ),
        "comparison_attainment_pct": Fact(
            comparison_pct, Unit.PERCENT,
            f"{comparison_period} attainment against quota by day {day}",
        ),
        "comparison_won_deal_count": Fact(
            float(len(comparison_won)), Unit.COUNT,
            f"Deals closed won in {comparison_period} by day {day}",
        ),
        "comparison_eventual_closed_won": Fact(
            comparison_eventual_closed_won, Unit.CURRENCY,
            f"{comparison_period} eventual closed-won total",
        ),
        "gap_pct": Fact(
            gap_pct, Unit.PERCENT,
            f"Gap between {period} and {comparison_period} at the same day of quarter",
        ),
        "day_of_quarter": Fact(float(day), Unit.COUNT, "Day of the quarter compared"),
        "period_year": Fact(float(year_of(period)), Unit.DATE, "Year of the current period"),
    }

    table = pd.DataFrame(
        [
            {
                "period": period,
                "grouping": intent.grouping,
                "segment": intent.segment or "",
                "closed_won": current_closed_won,
                "quota": current_quota,
                "attainment_pct": round(current_pct, 1),
                "comparison_period": comparison_period,
                "comparison_closed_won": comparison_closed_won,
                "comparison_quota": comparison_quota,
                "comparison_attainment_pct": round(comparison_pct, 1),
                "comparison_deals": len(comparison_won),
                "gap_pct": round(gap_pct, 1),
                "day_of_quarter": day,
            }
        ]
    )

    filters = {
        "current snapshot": f"{snapshot} snapshot",
        "current period membership": f"close_date between {start} and {end}",
        "comparison snapshot": f"{comparison_snapshot} snapshot (as reported, not restated)",
        "comparison period membership": (
            f"close_date between {comparison_start} and {cutoff} "
            f"(day {day} of {comparison_period})"
        ),
        "grouping": intent.grouping,
    }
    if intent.segment:
        filters["segment"] = intent.segment
    else:
        filters["scope"] = "no segment filter"

    template = (
        f"{period} attainment {_scope_phrase(intent)} is {current_pct:.1f} percent, "
        f"against {comparison_pct:.1f} percent for {comparison_period} at the same "
        f"day of quarter — a gap of {gap_pct:.1f} points. {period}: "
        f"{current_closed_won:,.0f} closed-won against a {current_quota:,.0f} quota. "
        f"{comparison_period} by day {day}: {comparison_closed_won:,.0f} closed-won "
        f"from {len(comparison_won)} deals against a {comparison_quota:,.0f} quota."
    )

    source_rows = pd.concat([current_rows, comparison_rows], ignore_index=True)

    return Result(
        facts=facts,
        table=table,
        source_rows=source_rows[SOURCE_COLUMNS].sort_values(["period", "close_date"]).reset_index(drop=True),
        filters=filters,
        snapshot=snapshot,
        definition_keys=(
            "comparison",
            "attainment",
            "period_membership",
            "quota_source",
        ),
        template=template,
    )


def _scope(rows: pd.DataFrame, intent: Intent) -> pd.DataFrame:
    if intent.segment:
        rows = rows[rows["segment"] == intent.segment]
    return rows


def _scope_phrase(intent: Intent) -> str:
    if intent.segment:
        return f"for the {intent.segment} segment"
    return "across the whole organization"
