"""Risk: best-case coverage per rep against quota, for a period still open.

Risk answers a different question than attainment: not what has closed, but
whether a rep can still make quota even if every open deal they have closes.
Best case is closed-won plus open pipeline, both filtered by period
membership the same way every other figure in the system is. Anyone below
100 percent is flagged, meaning they cannot make quota even in that best
case.

A pace-based rule is explicitly rejected as the underlying threshold: at day
32 of a 91-day quarter most reps have closed nothing, so pace would flag
nearly everyone and tell a leader nothing they can act on. The 100 percent
threshold used here is this system's own invention, not a Acme standard
— the `invented_risk_rule` flag says so on every risk answer.

Facts carry the organization rollup plus one fact per rep who clears 100
percent, keyed by rep and labelled with the rep's name, so the narrator can
name the good news without ever holding the full roster. A rep below the
threshold gets no fact, so prose can never name them — they live in the
table and the source rows instead. The shortfall against quota is
precomputed as its own fact, since the narrator is forbidden from
arithmetic and a gap in prose can never be a subtraction it performed.

Risk is inherently per-rep: a segment or manager figure would sum best cases
against a summed quota, hiding the individual shortfall the metric exists to
surface. Only overall and rep groupings are registered here.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pandas as pd

from ..domain import Fact, Intent, Result, Unit
from ..periods import bounds, day_of_quarter, days_in_quarter, snapshot_for, year_of
from ..registry import MetricRequest, metric

RISK_THRESHOLD_PCT = 100.0

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


@dataclass(frozen=True)
class RepRisk:
    """One rep's best-case coverage for the period."""

    rep_id: str
    rep: str
    quota: float
    closed_won: float
    open_pipeline: float
    best_case: float
    best_case_pct: float
    at_risk: bool


@dataclass(frozen=True)
class OrgRisk:
    """The organization rollup `_template` needs, bundled instead of
    travelling as five separate positional numbers."""

    best_case: float
    quota: float
    pct: float
    shortfall: float
    at_risk_count: int


@metric(
    name="risk",
    description=(
        "Best-case coverage per rep for a period still in progress: closed-won "
        "revenue plus open pipeline against quota. Below 100 percent means "
        "missing quota even if every open deal closes. The 100 percent threshold "
        "used here is invented for this analysis, not a Acme standard. "
        "Answers overall or for one rep."
    ),
    groupings=("overall", "rep"),
    intent_fields=("period", "grouping", "rep"),
    definition_keys=(
        "best_case_coverage",
        "period_membership",
        "open_deal",
        "quota_source",
    ),
    examples=(
        "which reps are at risk of missing Q2",
        "who is at risk of missing quota this quarter",
        "is Marcus Rivera at risk of missing quota this quarter",
    ),
)
def risk(request: MetricRequest) -> Result:
    intent = request.intent
    period = intent.period
    snapshot = snapshot_for(period)
    start, end = bounds(period)

    deals = request.data.deals(snapshot)
    rows = deals[deals["period"] == period]

    quotas = request.data.quotas
    scope = quotas[quotas["period"] == period]
    if intent.rep:
        scope = scope[scope["rep_name"] == intent.rep]
    scope = scope.sort_values("rep_name")

    per_rep = [_rep_figures(rows, row) for row in scope.itertuples()]
    table = pd.DataFrame([asdict(entry) for entry in per_rep]).drop(columns=["rep_id"])

    org_best_case = float(sum(entry.best_case for entry in per_rep))
    org_quota = float(sum(entry.quota for entry in per_rep))
    org = OrgRisk(
        best_case=org_best_case,
        quota=org_quota,
        pct=org_best_case / org_quota * 100 if org_quota else 0.0,
        shortfall=max(org_quota - org_best_case, 0.0),
        at_risk_count=sum(1 for entry in per_rep if entry.best_case_pct < RISK_THRESHOLD_PCT),
    )
    clearing = [entry for entry in per_rep if entry.best_case_pct >= RISK_THRESHOLD_PCT]

    facts = {
        "best_case": Fact(org.best_case, Unit.CURRENCY, "Best-case coverage"),
        "quota": Fact(org.quota, Unit.CURRENCY, f"{period} quota"),
        "best_case_pct": Fact(org.pct, Unit.PERCENT, "Best-case coverage against quota"),
        "shortfall": Fact(org.shortfall, Unit.CURRENCY, "Shortfall against quota"),
        "at_risk_count": Fact(
            float(org.at_risk_count), Unit.COUNT, "Reps below 100 percent best case"
        ),
        "clear_count": Fact(
            float(len(clearing)), Unit.COUNT, "Reps clearing 100 percent best case"
        ),
        "rep_count": Fact(float(len(per_rep)), Unit.COUNT, "Reps in scope"),
        "period_year": Fact(float(year_of(period)), Unit.DATE, "Year of the period"),
        "day_of_quarter": Fact(
            float(day_of_quarter(period, request.as_of)), Unit.COUNT, "Day of the quarter"
        ),
        "days_in_quarter": Fact(
            float(days_in_quarter(period)), Unit.COUNT, "Days in the quarter"
        ),
    }
    # One fact per rep who clears 100 percent, keyed by rep and labelled with
    # their name — the only channel through which a clearing rep's name can
    # reach the narrator. A rep who doesn't clear gets no fact here, so prose
    # can never name them; they still show up in `table` and `source_rows`.
    for entry in clearing:
        key = f"clears_{_slug(entry.rep_id)}"
        facts[key] = Fact(entry.best_case_pct, Unit.PERCENT, f"{entry.rep} best-case coverage")

    filters = {
        "snapshot": f"{snapshot} snapshot",
        "period membership": f"close_date between {start} and {end}",
        "grouping": intent.grouping,
    }
    if intent.rep:
        filters["rep"] = intent.rep
    else:
        filters["scope"] = "all reps"

    template = _template(intent, period, per_rep, clearing, org)

    scoped_ids = {entry.rep_id for entry in per_rep}
    source_rows = rows[rows["rep_id"].isin(scoped_ids) & (rows["is_won"] | rows["is_open"])]

    return Result(
        facts=facts,
        table=table,
        source_rows=source_rows[SOURCE_COLUMNS].sort_values("close_date").reset_index(drop=True),
        filters=filters,
        snapshot=snapshot,
        definition_keys=(
            "best_case_coverage",
            "period_membership",
            "open_deal",
            "quota_source",
        ),
        template=template,
    )


def _rep_figures(rows: pd.DataFrame, quota_row) -> RepRisk:
    rep_rows = rows[rows["rep_id"] == quota_row.rep_id]
    closed_won = float(rep_rows.loc[rep_rows["is_won"], "deal_value"].sum())
    open_pipeline = float(rep_rows.loc[rep_rows["is_open"], "deal_value"].sum())
    best_case = closed_won + open_pipeline
    quota = float(quota_row.quota)
    pct = round(best_case / quota * 100, 1) if quota else 0.0
    return RepRisk(
        rep_id=quota_row.rep_id,
        rep=quota_row.rep_name,
        quota=quota,
        closed_won=closed_won,
        open_pipeline=open_pipeline,
        best_case=best_case,
        best_case_pct=pct,
        at_risk=pct < RISK_THRESHOLD_PCT,
    )


def _slug(rep_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", rep_id.lower()).strip("_")


def _template(
    intent: Intent,
    period: str,
    per_rep: list[RepRisk],
    clearing: list[RepRisk],
    org: OrgRisk,
) -> str:
    if intent.rep:
        entry = per_rep[0]
        status = "clears" if entry.best_case_pct >= RISK_THRESHOLD_PCT else "is short of"
        return (
            f"{entry.rep} {status} {period} quota on best case: "
            f"{entry.best_case:,.0f} against a {entry.quota:,.0f} quota "
            f"({entry.best_case_pct:.1f} percent), from {entry.closed_won:,.0f} "
            f"closed-won plus {entry.open_pipeline:,.0f} open."
        )

    clear_names = ", ".join(entry.rep for entry in clearing)
    clear_sentence = f" {clear_names} clear it." if clear_names else " No rep clears it."
    return (
        f"{period} best-case coverage is {org.best_case:,.0f} against a "
        f"{org.quota:,.0f} quota ({org.pct:.1f} percent), short by {org.shortfall:,.0f}. "
        f"{org.at_risk_count} of {len(per_rep)} reps are below 100 percent best case."
        f"{clear_sentence}"
    )
