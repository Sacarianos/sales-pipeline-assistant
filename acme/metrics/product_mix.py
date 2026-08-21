"""Product mix: closed-won revenue and open pipeline for a period, broken
out by product line.

This is not attainment scoped to a product line. Attainment divides revenue
by quota, and quota is recorded per rep in this data (`data/Q2/reps.csv` has
one quota column per period, no product breakdown at all). There is no
per-product quota to divide by, so reporting a product-line "attainment
percentage" would mean inventing a denominator nobody supplied. This metric
reports the numerator only: what closed, what is still open, split by
product line, with no quota comparison implied or attempted.

Every deal in this data carries exactly one `product_line` value. That part
is a verified fact, not an assumption: no nulls in either snapshot, and the
value set is identical across both. What the file does not confirm is
whether that single tag is a strict one-product-per-deal rule or a
convention for recording a deal that actually bundles more than one product.
If any deal is a bundle, this total assigns its whole value to the one tag
recorded, which would overstate that product line and understate the
others. The `product_line_attribution` flag in `acme.flags` states this
plainly on every answer from this metric, since the split is computed and
shown, not withheld, and a computed number carries its assumption alongside
it rather than in place of it.
"""

from __future__ import annotations

import re

import pandas as pd

from ..domain import Fact, Result, Unit
from ..periods import bounds, day_of_quarter, days_in_quarter, snapshot_for, year_of
from ..registry import MetricRequest, metric

SOURCE_COLUMNS = [
    "deal_id",
    "account_name",
    "segment",
    "rep_name",
    "manager",
    "product_line",
    "stage",
    "deal_value",
    "close_date",
    "period",
    "loss_reason",
]


@metric(
    name="product_mix",
    description=(
        "Closed-won revenue and open pipeline for a period, broken out by "
        "product line. No quota comparison, since quotas in this data are "
        "recorded per rep, not per product. Every deal carries exactly one "
        "product-line tag; the answer discloses that a bundled deal, if one "
        "exists, would have its whole value assigned to that one tag."
    ),
    groupings=("overall",),
    intent_fields=("period",),
    definition_keys=("period_membership",),
    examples=(
        "how is our pipeline broken out by product line",
        "which product line is doing best this quarter",
    ),
)
def product_mix(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    snapshot = snapshot_for(period)
    start, end = bounds(period)

    deals = request.data.deals(snapshot)
    rows = deals[deals["period"] == period].sort_values(["product_line", "close_date"])

    won = rows[rows["is_won"]]
    opened = rows[rows["is_open"]]

    closed_won = float(won["deal_value"].sum())
    open_pipeline = float(opened["deal_value"].sum())

    product_lines = sorted(rows["product_line"].dropna().unique())
    per_line = []
    for product_line in product_lines:
        scoped = rows[rows["product_line"] == product_line]
        scoped_won = scoped[scoped["is_won"]]
        scoped_open = scoped[scoped["is_open"]]
        per_line.append(
            {
                "product_line": product_line,
                "closed_won": float(scoped_won["deal_value"].sum()),
                "open_pipeline": float(scoped_open["deal_value"].sum()),
                "deals": len(scoped),
                "won_deals": len(scoped_won),
            }
        )

    facts = {
        "closed_won": Fact(closed_won, Unit.CURRENCY, f"{period} closed-won revenue, all product lines"),
        "open_pipeline": Fact(open_pipeline, Unit.CURRENCY, f"{period} open pipeline, all product lines"),
        "deal_count": Fact(float(len(rows)), Unit.COUNT, "Deals closing in the period"),
        "period_year": Fact(float(year_of(period)), Unit.DATE, "Year of the period"),
        "day_of_quarter": Fact(
            float(day_of_quarter(period, request.as_of)), Unit.COUNT, "Day of the quarter"
        ),
        "days_in_quarter": Fact(
            float(days_in_quarter(period)), Unit.COUNT, "Days in the quarter"
        ),
    }
    for entry in per_line:
        slug = _slug(entry["product_line"])
        facts[f"closed_won_{slug}"] = Fact(
            entry["closed_won"], Unit.CURRENCY, f"{entry['product_line']}: closed-won revenue"
        )
        facts[f"open_pipeline_{slug}"] = Fact(
            entry["open_pipeline"], Unit.CURRENCY, f"{entry['product_line']}: open pipeline"
        )

    table = pd.DataFrame(
        [
            {
                "period": period,
                "product_line": entry["product_line"],
                "closed_won": entry["closed_won"],
                "open_pipeline": entry["open_pipeline"],
                "deals": entry["deals"],
                "won_deals": entry["won_deals"],
            }
            for entry in per_line
        ]
    )

    filters = {
        "snapshot": f"{snapshot} snapshot",
        "period membership": f"close_date between {start} and {end}",
        "grouping": "overall, broken out by product line",
    }

    template = _template(period, closed_won, open_pipeline, per_line)

    return Result(
        facts=facts,
        table=table,
        source_rows=rows[SOURCE_COLUMNS].reset_index(drop=True),
        filters=filters,
        snapshot=snapshot,
        definition_keys=("period_membership",),
        template=template,
    )


def _slug(product_line: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", product_line.lower()).strip("_")


def _template(
    period: str, closed_won: float, open_pipeline: float, per_line: list[dict]
) -> str:
    lines = ", ".join(
        f"{entry['product_line']} {entry['closed_won']:,.0f}" for entry in per_line
    )
    return (
        f"{period} closed-won revenue by product line: {lines}, totaling "
        f"{closed_won:,.0f} against {open_pipeline:,.0f} still open across all "
        "product lines."
    )
