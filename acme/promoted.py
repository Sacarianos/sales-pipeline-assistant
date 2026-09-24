"""The runtime every promoted metric calls. See the V3 spec.

A promoted metric file holds a plan template as data: a frame of `deals`,
`quotas`, or `reps`, plus the filters, grouping, and aggregate the
exploratory lane ran. `compute_plan` turns that template into a concrete
plan for one question: the snapshot that owns the asked period, a filter to
that period, and a filter for whichever of segment, rep, and manager the
question names. The concrete plan then runs through the same checker and
the same pandas as the exploratory lane, so nothing written by a model
executes here either.
"""

from __future__ import annotations

from .domain import Intent, Result
from .periods import bounds, snapshot_for
from .query_plan import PlanRejection, QueryPlan, run
from .registry import MetricRequest

# Which frame column each scope field of an intent filters on. Segment on a
# deal and segment on its rep agree on every row in both snapshots, so the
# deal's own column is safe to use.
SCOPE_COLUMNS = {"segment": "segment", "rep": "rep_name", "manager": "manager"}

# Frames that hold more than one period and so get scoped to the asked one.
PERIOD_FRAMES = ("deals", "quotas")


class PromotedPlanFailed(RuntimeError):
    """A promoted plan that doesn't run is a bug in the metric file, never a
    refusal a reader should see, so it raises instead of refusing."""


def concrete_plan(template: dict, intent: Intent) -> tuple[QueryPlan, str]:
    """The plan for one question, and the snapshot it reads."""
    snapshot = snapshot_for(intent.period)
    frame = template["frame"]
    filters = list(template.get("filters", []))
    if frame in PERIOD_FRAMES:
        filters.append({"column": "period", "op": "eq", "value": intent.period})
    for field, column in SCOPE_COLUMNS.items():
        value = getattr(intent, field)
        if value:
            filters.append({"column": column, "op": "eq", "value": value})
    frame_name = f"deals_{snapshot.lower()}" if frame == "deals" else frame
    return QueryPlan(**{**template, "frame": frame_name, "filters": filters}), snapshot


def compute_plan(
    request: MetricRequest, template: dict, *, definition_keys: tuple[str, ...]
) -> Result:
    # Imported here because the fallback lane imports the router, which
    # imports the catalog, which walks the registry this module's callers
    # register into.
    from .fallback import display_table, facts_for, frames, schemas, template_for

    intent = request.intent
    plan, snapshot = concrete_plan(template, intent)
    outcome = run(
        plan,
        frames(request.data),
        schemas(request.data),
        trusted_columns=frozenset(SCOPE_COLUMNS.values()),
    )
    if isinstance(outcome, PlanRejection):
        raise PromotedPlanFailed(outcome.reason)

    filters = {"snapshot": f"{snapshot} snapshot"}
    if template["frame"] == "deals":
        start, end = bounds(intent.period)
        filters["period membership"] = f"close_date between {start} and {end}"
    scope = [f"{field} {getattr(intent, field)}" for field in SCOPE_COLUMNS if getattr(intent, field)]
    filters["scope"] = ", ".join(scope) if scope else "no rep, segment, or manager filter"
    filters["query"] = outcome.description

    facts = facts_for(plan, outcome)
    return Result(
        facts=facts,
        table=display_table(outcome.value),
        source_rows=outcome.rows,
        filters=filters,
        snapshot=snapshot,
        definition_keys=definition_keys,
        template=template_for(outcome, facts),
    )


__all__ = ["PERIOD_FRAMES", "SCOPE_COLUMNS", "PromotedPlanFailed", "compute_plan", "concrete_plan"]
