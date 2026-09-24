"""The exploratory fallback lane: a question the registry doesn't cover
reaches a generator, comes back as a structured query plan, runs through
`acme.query_plan`, and returns an answer instead of a plain refusal.

`attempt` is the one entry point, mirroring how `router.route` and
`narrator.narrate` each hide their own split behind a single call. It
returns an `Answered` when the plan ran, a `Declined` carrying the reason
when the generator declined or the plan was rejected, and `None` when the
lane couldn't try at all because there is no client or the API failed. The
pipeline turns both of the last two into the ordinary catalog refusal, with
the reason attached when there is one.

The generator sees column names, kinds, and the distinct values of
low-cardinality columns, the same shape the router prompt already uses. It
never receives a data row. Identifier and date columns are left out of the
value listing because their distinct values are close to the row count.
The columns a refused topic rests on, region on both sides, are hidden from
the plan entirely.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from pydantic import ValidationError

from .config import ROUTER_MODEL
from .domain import Answered, Fact, Unit
from .flags import evaluate_for_snapshot
from .loading import Data
from .narrator import narrate
from .periods import period_for_snapshot
from .query_log import LogRecord, Outcome, QueryLog
from .query_plan import (
    ROW_CAP,
    FrameSchema,
    PlanRejection,
    QueryPlan,
    QueryResult,
    describe_frames,
    run,
    tool_schema,
)
from .router import REFUSED_TOPICS

FRAME_NAMES = ("deals_q1", "deals_q2", "quotas", "reps")

# The noun and scope each frame's plain English description uses.
FRAME_LABELS = {
    "deals_q1": ("deals", "the Q1 snapshot"),
    "deals_q2": ("deals", "the Q2 snapshot"),
    "quotas": ("quota rows", "the quota table"),
    "reps": ("reps", "the rep roster"),
}

# A refused topic has to stay refused in this lane too. Refusing the word
# "region" ahead of routing isn't enough on its own, since "which territory
# has the most pipeline" never says it. Hiding the columns means no plan can
# read them however the question is phrased.
HIDDEN_COLUMNS = frozenset(column for topic in REFUSED_TOPICS for column in topic.columns)

# Totals, averages, and listings of these columns are dollar figures.
CURRENCY_COLUMNS = frozenset({"deal_value", "quota", "quota_q1_2026", "quota_q2_2026"})

# A result this small can be summarized as individually labelled Facts a
# narrator could cite. Above it, no per-row facts are produced at all, so the
# verifier has nothing to let a citation of an unvetted row pass against, and
# the template's row count is what publishes instead.
FACT_ROW_CAP = 8

TOOL_NAME = "plan_query"


@dataclass(frozen=True)
class Declined:
    """The lane tried and couldn't answer. `reason` says why, in words the
    reader sees on the refusal."""

    reason: str


def _frames(data: Data) -> dict[str, pd.DataFrame]:
    """The frames the lane may name, bound to the same objects the metrics
    use. Named per snapshot, and a plan reads exactly one, since silently
    blending the two snapshots would reintroduce the exact error the
    reconciler exists to prevent."""
    return {
        "deals_q1": data.deals("Q1"),
        "deals_q2": data.deals("Q2"),
        "quotas": data.quotas,
        "reps": data.reps,
    }


def _schemas(data: Data) -> dict[str, FrameSchema]:
    return describe_frames(_frames(data), hidden_columns=HIDDEN_COLUMNS, labels=FRAME_LABELS)


def _tool_schema(data: Data) -> dict:
    return tool_schema(_schemas(data))


def _describe_frame(schema: FrameSchema) -> str:
    lines = [f"  {schema.name}: {schema.noun} in {schema.scope}, {schema.row_count} rows"]
    for column in schema.columns.values():
        values = f": {list(column.values)}" if column.values else ""
        lines.append(f"    - {column.name} ({column.kind}){values}")
    return "\n".join(lines)


def _system_prompt(data: Data) -> str:
    """Everything the generator gets: frame schemas, never a data row."""
    frames = "\n".join(_describe_frame(schema) for schema in _schemas(data).values())
    return (
        "You turn a sales leader's question into a query plan, recorded "
        f"through the {TOOL_NAME} tool. You never see any deal-level data, "
        "only the frame schemas below.\n\n"
        f"Frames available:\n{frames}\n\n"
        "Rules:\n"
        "- A plan reads exactly one frame. deals_q1 and deals_q2 are two "
        "snapshots of the same deals and are never combined. If the question "
        "doesn't name a quarter, read deals_q2, the current snapshot.\n"
        "- Filter a category column only with one of the values listed for it.\n"
        "- Prefer the 'period' column over comparing close_date. When you do "
        "filter a date, write it YYYY-MM-DD.\n"
        "- To answer with numbers, set an aggregate, optionally grouped. To "
        "answer with a list of rows, leave the aggregate out and name the "
        "columns to show.\n"
        "- If the question needs a column that isn't listed above, set "
        "decline_reason and leave every other field out. Decline rather "
        "than substitute the nearest-looking column.\n"
    )


def _generate(question: str, data: Data, client: object) -> dict | None:
    """The generator's raw tool input, or `None` on any API failure."""
    try:
        message = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=1024,
            system=_system_prompt(data),
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Record the query plan that answers the question, or a decline.",
                    "input_schema": _tool_schema(data),
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": question}],
        )
        block = next(b for b in message.content if getattr(b, "type", None) == "tool_use")
        return dict(block.input)
    except Exception:
        return None


def _unit(plan: QueryPlan, column: str | None) -> Unit:
    spec = plan.aggregate
    if spec is not None and spec.function in ("count", "nunique"):
        return Unit.COUNT
    if column in CURRENCY_COLUMNS:
        return Unit.CURRENCY
    return Unit.NUMBER


def _is_numeric_column(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def _facts(plan: QueryPlan, result: QueryResult) -> dict[str, Fact]:
    """Facts for whatever shape the plan returned.

    The count of rows the filters matched is always a fact, so the narrator
    always has one true thing it can say. Individual row values join it only
    up to `FACT_ROW_CAP`. Past that, no per-row facts exist at all, so the
    verifier has nothing to validate an unvetted row citation against.
    """
    facts = {"matched_rows": Fact(float(result.matched_rows), Unit.COUNT, "Rows the filters matched")}
    value = result.value
    agg_column = plan.aggregate.column if plan.aggregate else None

    if not isinstance(value, pd.DataFrame):
        if value is not None:
            facts["result"] = Fact(float(value), _unit(plan, agg_column), result.result_label)
        return facts

    facts["row_count"] = Fact(float(result.row_count), Unit.COUNT, "Rows returned by the query")
    if len(value) > FACT_ROW_CAP:
        return facts
    # A grouped result is labelled by its group keys. A listing is labelled
    # by its first two text columns, so a deal reads as its ID and account
    # and the label still fits the figures panel.
    numeric = [c for c in value.columns if _is_numeric_column(value[c])]
    if plan.aggregate:
        label_columns = list(plan.group_by)
    else:
        label_columns = [c for c in value.columns if c not in numeric][:2]
    value_columns = [c for c in numeric if c not in label_columns]
    for i, row in enumerate(value.to_dict("records")):
        names = ["blank" if pd.isna(row[c]) else str(row[c]) for c in label_columns]
        label = " / ".join(names) if names else f"row {i + 1}"
        for column in value_columns:
            if pd.isna(row[column]):
                continue
            unit = _unit(plan, agg_column if plan.aggregate else column)
            facts[f"row{i}_{column}"] = Fact(float(row[column]), unit, f"{label}: {column}")
    return facts


def _template(result: QueryResult, facts: dict[str, Fact]) -> str:
    if isinstance(result.value, pd.DataFrame):
        count = result.row_count
        note = f", showing the first {ROW_CAP}" if result.truncated else ""
        return f"This exploratory query returned {count} row{'s' if count != 1 else ''}{note}."
    if "result" in facts:
        return f"{result.result_label}: {facts['result'].formatted()}."
    return "No rows matched this query, so there is nothing to compute."


def _display(value: object) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.reset_index(drop=True)
    return pd.DataFrame([{"result": value}])


def attempt(
    question: str,
    data: Data,
    client: object | None,
    *,
    router_mode: str = "online",
    log: QueryLog | None = None,
) -> Answered | Declined | None:
    """Try to answer `question` from the fallback lane.

    Every attempt appends exactly one record to `log` when one is given. No
    client means no attempt, so nothing is logged then.
    """
    if client is None:
        return None

    def record(outcome: Outcome, **fields) -> None:
        if log is not None:
            log.append(LogRecord(question=question, outcome=outcome, **fields))

    raw = _generate(question, data, client)
    if raw is None:
        record("unavailable", reason="the generator call failed")
        return None
    try:
        plan = QueryPlan(**raw)
    except ValidationError as exc:
        reason = f"the query written for it didn't match the plan format: {exc.errors()[0]['msg']}"
        record("rejected", plan=raw, reason=reason)
        return Declined(reason)
    if plan.decline_reason:
        record("declined", reason=plan.decline_reason)
        return Declined(plan.decline_reason)

    outcome = run(plan, _frames(data), _schemas(data))
    if isinstance(outcome, PlanRejection):
        record("failed" if outcome.ran else "rejected", plan=raw, reason=outcome.reason)
        verb = "failed" if outcome.ran else "was rejected"
        return Declined(f"the query written for it {verb}: {outcome.reason}")
    record("answered", plan=raw, matched_rows=outcome.matched_rows, row_count=outcome.row_count)

    facts = _facts(plan, outcome)
    table = _display(outcome.value)
    filters = {
        "frame read": plan.frame,
        "rows matched": f"{outcome.matched_rows}",
        "row cap": f"first {ROW_CAP} of {outcome.row_count}" if outcome.truncated else "no truncation",
    }

    # A stale close date and a partial period are properties of the
    # snapshot a plan read, not of the lane that read it, so those caveats
    # still run here. See `flags.evaluate_for_snapshot` for why only the
    # snapshot-level rules apply. A plan over quotas or reps reads no deals
    # snapshot and gets the current quarter's caveats, the same default the
    # generator is told to use.
    snapshot = "Q1" if plan.frame == "deals_q1" else "Q2"
    flags = evaluate_for_snapshot(period_for_snapshot(snapshot), snapshot, data)

    # Same contract as a metric's answer: the narrator sees only the
    # question, a restatement, and the facts just derived, and its prose is
    # verified against those facts before publishing.
    restated = f"Reading this as an exploratory query: {outcome.description}"
    narration = narrate(question, restated, facts, _template(outcome, facts), client)

    return Answered(
        lane="exploratory",
        expression=outcome.code,
        query_description=outcome.description,
        restated=restated,
        prose=narration.prose,
        prose_source=narration.source,
        verified_figures=narration.verified_figures,
        narrator_blocked=narration.blocked,
        facts=facts,
        flags=flags,
        table=table,
        source_rows=table,
        filters=filters,
        snapshot=snapshot,
        intent=None,
        router_mode=router_mode,
    )


__all__ = ["Declined", "attempt"]
