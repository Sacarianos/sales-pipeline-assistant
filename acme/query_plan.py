"""The structured query plan the fallback lane runs. Recorded in ADR-0007.

The generator fills a plan through a forced tool, the same way the router
fills an `Intent`. It names one frame and a fixed set of operations: filters,
grouping, one aggregate, sort, and limit. This module checks the plan against
the frame schemas and then runs it with pandas code written here. Nothing the
model writes is ever evaluated. A filter value is data, compared against a
column, and a string holding code is just a string that matches no rows.

`run` returns either a `QueryResult` or a `PlanRejection`, and a rejected plan
never partly runs. It is never repaired either, because a repaired plan
answers a question nobody asked.

Every result carries two readings of the plan, both built from the plan and
never from the model's prose. `description` is a plain English sentence for
the sales leader. `code` is the equivalent pandas an analyst can paste into a
notebook to reproduce the figure. The tests pin `code` to the result that
actually ran, so the two can't drift apart.
"""

from __future__ import annotations

import datetime
import operator
from dataclasses import dataclass
from typing import Callable, Literal, Union

import pandas as pd
from pydantic import BaseModel, Field

# A result longer than this truncates for display. The full count still
# reports, so a reader knows how much was cut.
ROW_CAP = 200
MAX_GROUP_BY = 2
LOW_CARDINALITY_THRESHOLD = 15

# The sort key that means "the aggregate's own value" on a grouped plan.
RESULT = "result"

ColumnKind = Literal["number", "bool", "category", "text", "date"]
Op = Literal["eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte"]
Function = Literal["count", "nunique", "sum", "mean", "median", "min", "max"]

ORDERED_OPS = ("gt", "gte", "lt", "lte")
LIST_OPS = ("in", "not_in")

# Which column kinds each aggregate may read. Count reads no column at all.
AGGREGATE_KINDS: dict[str, tuple[ColumnKind, ...]] = {
    "nunique": ("number", "bool", "category", "text", "date"),
    "sum": ("number", "bool"),
    "mean": ("number", "bool"),
    "median": ("number",),
    "min": ("number",),
    "max": ("number",),
}
GROUPABLE_KINDS: tuple[ColumnKind, ...] = ("bool", "category", "text", "date")

_COMPARISONS: dict[str, tuple[str, Callable]] = {
    "eq": ("==", operator.eq),
    "ne": ("!=", operator.ne),
    "gt": (">", operator.gt),
    "gte": (">=", operator.ge),
    "lt": ("<", operator.lt),
    "lte": ("<=", operator.le),
}

_AGGREGATE_LABELS = {
    "sum": "Total {}",
    "mean": "Average {}",
    "median": "Median {}",
    "min": "Smallest {}",
    "max": "Largest {}",
    "nunique": "Number of distinct {} values",
}


@dataclass(frozen=True)
class Column:
    name: str
    kind: ColumnKind
    # Every distinct value, for a category column only. A filter on a
    # category must name one of these, so a typo refuses instead of silently
    # matching nothing.
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrameSchema:
    name: str
    noun: str
    scope: str
    row_count: int
    columns: dict[str, Column]
    # Columns the frame has but a plan may not read. Kept by name so a plan
    # naming one is told it's withheld, not that it doesn't exist.
    hidden: frozenset[str] = frozenset()


def _column(name: str, series: pd.Series) -> Column:
    if pd.api.types.is_bool_dtype(series):
        return Column(name, "bool")
    if pd.api.types.is_numeric_dtype(series):
        return Column(name, "number")
    present = series.dropna()
    if len(present) and all(isinstance(v, datetime.date) for v in present):
        return Column(name, "date")
    values = sorted({str(v) for v in present.unique()})
    if len(values) <= LOW_CARDINALITY_THRESHOLD:
        return Column(name, "category", tuple(values))
    return Column(name, "text")


def describe_frames(
    frames: dict[str, pd.DataFrame],
    *,
    hidden_columns: frozenset[str] = frozenset(),
    labels: dict[str, tuple[str, str]] | None = None,
) -> dict[str, FrameSchema]:
    """Schemas for the frames a plan may read.

    A hidden column isn't in the tool's enums, the generator's prompt, or a
    row listing, and a plan naming it is rejected as withheld.
    `labels` maps a frame name to the noun and scope its description uses.
    """
    labels = labels or {}
    schemas = {}
    for name, frame in frames.items():
        noun, scope = labels.get(name, ("rows", f"the {name} frame"))
        columns = {
            column: _column(column, frame[column])
            for column in frame.columns
            if column not in hidden_columns
        }
        hidden = frozenset(frame.columns) & hidden_columns
        schemas[name] = FrameSchema(name, noun, scope, len(frame), columns, hidden)
    return schemas


Scalar = Union[bool, int, float, str]


class Filter(BaseModel):
    column: str
    op: Op
    value: Union[Scalar, list[Scalar]]


class Aggregate(BaseModel):
    function: Function
    column: str | None = None


class QueryPlan(BaseModel):
    """What the generator returns: a plan to run, or a decline."""

    frame: str | None = None
    filters: list[Filter] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregate: Aggregate | None = None
    columns: list[str] = Field(default_factory=list)
    sort_by: str | None = None
    descending: bool = True
    limit: int | None = None
    decline_reason: str | None = None
    # True when this plan refines the previous exploratory plan in the
    # conversation, like "just for Enterprise". The answer then says what
    # changed. Never read by the checker or the runner.
    refines_previous: bool = False


@dataclass(frozen=True)
class QueryResult:
    # A DataFrame for a listing or a grouped aggregate. A plain number for an
    # ungrouped aggregate, or None when that aggregate had no rows to read.
    value: object
    row_count: int | None
    truncated: bool
    matched_rows: int
    # The rows the filters matched, with withheld columns left out.
    rows: pd.DataFrame
    code: str
    description: str
    result_label: str


@dataclass(frozen=True)
class PlanRejection:
    reason: str
    # True when the plan passed the checker and failed while running, False
    # when the checker stopped it before anything ran.
    ran: bool = False


class _Rejected(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _human(column: str) -> str:
    return column.replace("_", " ")


# --- checking -------------------------------------------------------------


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_values(column: Column, op: str, values: list, *, trusted: bool = False) -> None:
    if op in ORDERED_OPS and column.kind not in ("number", "date"):
        raise _Rejected(f"can't compare '{column.name}' with {op}, it's a {column.kind} column")
    for value in values:
        if column.kind == "bool":
            if op not in ("eq", "ne") or not isinstance(value, bool):
                raise _Rejected(f"'{column.name}' holds true or false, so filter it with eq or ne and a true or false value")
        elif column.kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _Rejected(f"'{column.name}' needs a number, got {value!r}")
        elif column.kind == "date":
            if not _is_iso_date(value):
                raise _Rejected(f"'{column.name}' needs a date written YYYY-MM-DD")
        elif column.kind == "category":
            if not isinstance(value, str):
                raise _Rejected(f"'{column.name}' needs text, got {value!r}")
            if not trusted and value not in column.values:
                raise _Rejected(
                    f"{value!r} is not a value of '{column.name}'. Its values are {list(column.values)}"
                )
        elif not isinstance(value, str):
            raise _Rejected(f"'{column.name}' needs text, got {value!r}")


def _check_filter(column: Column, spec: Filter, *, trusted: bool = False) -> None:
    if spec.op in LIST_OPS:
        if not isinstance(spec.value, list) or not spec.value:
            raise _Rejected(f"'{spec.op}' needs a list of values")
        values = spec.value
    else:
        if isinstance(spec.value, list):
            raise _Rejected(f"'{spec.op}' takes a single value, not a list")
        values = [spec.value]
    _check_values(column, spec.op, values, trusted=trusted)


def _check_aggregate(spec: Aggregate, lookup: Callable[[str], Column], group_by: list[str]) -> None:
    if spec.function == "count":
        if spec.column is not None:
            raise _Rejected("count counts rows, so leave its column empty")
        return
    if spec.column is None:
        raise _Rejected(f"{spec.function} needs a column")
    column = lookup(spec.column)
    if column.kind not in AGGREGATE_KINDS[spec.function]:
        raise _Rejected(f"can't take {spec.function} of '{column.name}', it's a {column.kind} column")
    if spec.column in group_by:
        raise _Rejected(f"'{spec.column}' is also grouped by, so aggregating it per group means nothing")


def _listing_columns(plan: QueryPlan, schema: FrameSchema) -> list[str]:
    return list(plan.columns) or list(schema.columns)


def _check(
    plan: QueryPlan, schemas: dict[str, FrameSchema], trusted_columns: frozenset[str]
) -> FrameSchema:
    if not plan.frame:
        raise _Rejected("a plan must name a frame")
    schema = schemas.get(plan.frame)
    if schema is None:
        raise _Rejected(f"'{plan.frame}' is not one of the frames this lane exposes")

    def lookup(name: str) -> Column:
        if name in schema.hidden:
            raise _Rejected(f"'{name}' is withheld from exploratory queries")
        column = schema.columns.get(name)
        if column is None:
            raise _Rejected(f"'{name}' is not a column of {plan.frame}")
        return column

    for spec in plan.filters:
        _check_filter(lookup(spec.column), spec, trusted=spec.column in trusted_columns)

    if len(plan.group_by) > MAX_GROUP_BY:
        raise _Rejected(f"a plan may group by at most {MAX_GROUP_BY} columns")
    if len(set(plan.group_by)) != len(plan.group_by):
        raise _Rejected("a plan may not group by the same column twice")
    for name in plan.group_by:
        column = lookup(name)
        if column.kind not in GROUPABLE_KINDS:
            raise _Rejected(f"can't group by '{name}', it's a {column.kind} column")

    if plan.aggregate is None:
        if plan.group_by:
            raise _Rejected("grouping needs an aggregate to compute for each group")
        for name in plan.columns:
            lookup(name)
        if plan.sort_by is not None and plan.sort_by not in _listing_columns(plan, schema):
            raise _Rejected(f"can't sort by '{plan.sort_by}', it isn't one of the columns shown")
    else:
        if plan.columns:
            raise _Rejected("columns only apply to a row listing, not to an aggregate")
        _check_aggregate(plan.aggregate, lookup, plan.group_by)
        if not plan.group_by:
            if plan.sort_by is not None or plan.limit is not None:
                raise _Rejected(
                    "an aggregate with no grouping returns a single number, so it can't be sorted or limited"
                )
        elif plan.sort_by is not None and plan.sort_by != RESULT and plan.sort_by not in plan.group_by:
            raise _Rejected(f"can't sort by '{plan.sort_by}'. Use '{RESULT}' or one of the grouped columns")

    if plan.limit is not None and not 1 <= plan.limit <= ROW_CAP:
        raise _Rejected(f"limit must be between 1 and {ROW_CAP}")
    return schema


# --- running --------------------------------------------------------------


def _literal(column: Column, value: Scalar) -> tuple[object, str]:
    """The value a filter compares against, and how the code shows it."""
    if column.kind == "date":
        day = datetime.date.fromisoformat(value)
        return day, f"datetime.date({day.year}, {day.month}, {day.day})"
    return value, repr(value)


def _filter_rows(plan: QueryPlan, schema: FrameSchema, frame: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if not plan.filters:
        return frame, plan.frame
    mask = pd.Series(True, index=frame.index)
    parts = []
    for spec in plan.filters:
        column = schema.columns[spec.column]
        series = frame[spec.column]
        ref = f"{plan.frame}[{spec.column!r}]"
        if spec.op in LIST_OPS:
            literals = [_literal(column, v) for v in spec.value]
            matched = series.isin([value for value, _ in literals])
            code = f"{ref}.isin([{', '.join(text for _, text in literals)}])"
            if spec.op == "not_in":
                matched, code = ~matched, f"~{code}"
        else:
            value, text = _literal(column, spec.value)
            symbol, compare = _COMPARISONS[spec.op]
            matched = compare(series, value)
            code = f"{ref} {symbol} {text}"
        mask &= matched
        parts.append(f"({code})")
    return frame[mask], f"{plan.frame}[{' & '.join(parts)}]"


def _sorted_and_limited(
    out: pd.DataFrame, code: str, sort_key: str | None, plan: QueryPlan
) -> tuple[pd.DataFrame, str]:
    if sort_key is not None:
        ascending = not plan.descending
        out = out.sort_values(sort_key, ascending=ascending)
        code += f".sort_values({sort_key!r}, ascending={ascending})"
    if plan.limit is not None:
        out = out.head(plan.limit)
        code += f".head({plan.limit})"
    return out, code


def _plain(value: object) -> object:
    """A numpy scalar as a Python one, and NaN as None."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    return value


def _result_column(spec: Aggregate) -> str:
    return "count" if spec.function == "count" else f"{spec.function}_{spec.column}"


def _execute(
    plan: QueryPlan, schema: FrameSchema, frame: pd.DataFrame
) -> tuple[object, pd.DataFrame, str]:
    """The result, the rows the filters matched, and the code that ran."""
    rows, rows_code = _filter_rows(plan, schema, frame)
    spec = plan.aggregate

    if spec is None:
        columns = _listing_columns(plan, schema)
        out, code = _sorted_and_limited(rows[columns], f"{rows_code}[{columns!r}]", plan.sort_by, plan)
        return out, rows, code

    if not plan.group_by:
        if spec.function == "count":
            return len(rows), rows, f"len({rows_code})"
        value = getattr(rows[spec.column], spec.function)()
        return _plain(value), rows, f"{rows_code}[{spec.column!r}].{spec.function}()"

    name = _result_column(spec)
    groups = rows.groupby(plan.group_by, dropna=False)
    code = f"{rows_code}.groupby({plan.group_by!r}, dropna=False)"
    if spec.function == "count":
        per_group = groups.size()
        code += ".size()"
    else:
        per_group = getattr(groups[spec.column], spec.function)()
        code += f"[{spec.column!r}].{spec.function}()"
    out = per_group.reset_index(name=name)
    code += f".reset_index(name={name!r})"
    sort_key = name if plan.sort_by == RESULT else plan.sort_by
    out, code = _sorted_and_limited(out, code, sort_key, plan)
    return out, rows, code


# --- describing -----------------------------------------------------------


def _value_text(value: Scalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{int(value):,}" if float(value).is_integer() else f"{value:,}"
    return str(value)


def _filter_text(column: Column, spec: Filter, noun: str) -> str:
    name = _human(spec.column)
    if spec.op in LIST_OPS:
        values = ", ".join(_value_text(v) for v in spec.value)
        return f"{name} is {'one' if spec.op == 'in' else 'none'} of {values}"
    if column.kind == "bool" and spec.column.startswith("is_"):
        holds = (spec.op == "eq") == spec.value
        singular = noun[:-1] if noun.endswith("s") else noun
        return f"the {singular} is {'' if holds else 'not '}{_human(spec.column[3:])}"
    value = _value_text(spec.value)
    if spec.op == "eq":
        return f"{name} is {value}"
    if spec.op == "ne":
        return f"{name} is not {value}"
    dated = column.kind == "date"
    phrase = {
        "gt": "is after" if dated else "is above",
        "gte": "is on or after" if dated else "is at least",
        "lt": "is before" if dated else "is below",
        "lte": "is on or before" if dated else "is at most",
    }[spec.op]
    return f"{name} {phrase} {value}"


def _order_text(kind: ColumnKind | None, descending: bool) -> str:
    if kind == "date":
        return "latest first" if descending else "earliest first"
    if kind in ("category", "text", "bool"):
        return "Z to A" if descending else "A to Z"
    return "highest first" if descending else "lowest first"


def _result_label(plan: QueryPlan, schema: FrameSchema) -> str:
    spec = plan.aggregate
    if spec is None:
        return "Rows"
    if spec.function == "count":
        return f"Number of {schema.noun}"
    return _AGGREGATE_LABELS[spec.function].format(_human(spec.column))


def _describe(plan: QueryPlan, schema: FrameSchema) -> str:
    spec = plan.aggregate
    if spec is None:
        text = f"{schema.noun.capitalize()} in {schema.scope}"
    elif spec.function == "count":
        text = f"{_result_label(plan, schema)} in {schema.scope}"
    else:
        text = f"{_result_label(plan, schema)} across {schema.noun} in {schema.scope}"

    if plan.filters:
        text += " where " + " and ".join(
            _filter_text(schema.columns[f.column], f, schema.noun) for f in plan.filters
        )
    if spec is None and plan.columns:
        text += ", showing " + ", ".join(_human(c) for c in plan.columns)
    if plan.group_by:
        text += ", grouped by " + " and ".join(_human(c) for c in plan.group_by)
    if plan.sort_by is not None:
        text += ", " + _sort_text(plan, schema)
    if plan.limit is not None:
        text += f", {'top' if plan.sort_by is not None else 'first'} {plan.limit}"
    return text + "."


def _sort_text(plan: QueryPlan, schema: FrameSchema) -> str:
    if plan.sort_by == RESULT:
        return f"sorted by the result, {_order_text(None, plan.descending)}"
    kind = schema.columns[plan.sort_by].kind
    return f"sorted by {_human(plan.sort_by)}, {_order_text(kind, plan.descending)}"


def _filter_key(spec: Filter) -> tuple:
    return (spec.column, spec.op, repr(spec.value))


def describe_change(before: dict, after: dict, schemas: dict[str, FrameSchema]) -> str:
    """What changed from one plan to the next, in plain English.

    Built from the two plans, never from model prose, so a refinement shows
    the reader exactly what it did to the last query. Both plans have
    already passed the checker, so every column they name is in `schemas`.
    """
    old, new = QueryPlan(**before), QueryPlan(**after)
    old_schema, new_schema = schemas[old.frame], schemas[new.frame]
    parts = []

    if new.frame != old.frame:
        parts.append(f"now reads {new_schema.scope} instead of {old_schema.scope}")

    old_filters = {_filter_key(f): f for f in old.filters}
    new_filters = {_filter_key(f): f for f in new.filters}
    for key, spec in new_filters.items():
        if key not in old_filters:
            parts.append("added " + _filter_text(new_schema.columns[spec.column], spec, new_schema.noun))
    for key, spec in old_filters.items():
        if key not in new_filters:
            parts.append("removed " + _filter_text(old_schema.columns[spec.column], spec, old_schema.noun))

    if new.aggregate != old.aggregate:
        if new.aggregate is None:
            parts.append("now lists rows")
        else:
            label = _result_label(new, new_schema)
            parts.append(f"now computes {label[0].lower()}{label[1:]}")

    shape = []
    if new.group_by != old.group_by:
        shape.append(
            "grouped by " + " and ".join(_human(c) for c in new.group_by) if new.group_by else "not grouped"
        )
    if new.columns != old.columns and new.columns:
        shape.append("showing " + ", ".join(_human(c) for c in new.columns))
    if (new.sort_by, new.descending) != (old.sort_by, old.descending):
        shape.append(_sort_text(new, new_schema) if new.sort_by is not None else "not sorted")
    if new.limit != old.limit:
        shape.append(f"top {new.limit}" if new.limit is not None else "not limited")
    if shape:
        parts.append("now " + ", ".join(shape))

    if not parts:
        return "Same query as your last one."
    return "Changed from your last query: " + "; ".join(parts) + "."


# --- entry points ---------------------------------------------------------


def run(
    plan: QueryPlan,
    frames: dict[str, pd.DataFrame],
    schemas: dict[str, FrameSchema],
    *,
    trusted_columns: frozenset[str] = frozenset(),
) -> Union[QueryResult, PlanRejection]:
    """Check the plan, then run it. A plan that fails the check never runs.

    A filter on a `trusted_columns` column skips the rule that a category
    value must be one the column holds. That rule catches a model's typo.
    A caller filtering on a value it already validated, like a promoted
    metric scoping to a rep with no deals this quarter, wants zero rows
    instead of a rejection.
    """
    try:
        schema = _check(plan, schemas, trusted_columns)
    except _Rejected as exc:
        return PlanRejection(exc.reason)

    try:
        value, rows, code = _execute(plan, schema, frames[plan.frame])
    except Exception as exc:  # noqa: BLE001 - a runtime failure is a refusal, not a crash
        return PlanRejection(f"the query failed while running: {type(exc).__name__}: {exc}", ran=True)

    row_count, truncated = None, False
    if isinstance(value, pd.DataFrame):
        row_count = len(value)
        if row_count > ROW_CAP:
            value, truncated = value.head(ROW_CAP), True

    return QueryResult(
        value=value,
        row_count=row_count,
        truncated=truncated,
        matched_rows=len(rows),
        rows=rows[list(schema.columns)].reset_index(drop=True),
        code=code,
        description=_describe(plan, schema),
        result_label=_result_label(plan, schema),
    )


def tool_schema(schemas: dict[str, FrameSchema]) -> dict:
    """The generator's tool input schema, with frames and columns as enums.

    The enums help the model. They are not the boundary: `run` checks every
    name again against the frame the plan actually names.
    """
    columns = sorted({name for schema in schemas.values() for name in schema.columns})
    column = {"type": "string", "enum": columns}
    scalar = {"type": ["string", "number", "boolean"]}
    return {
        "type": "object",
        "properties": {
            "frame": {
                "type": "string",
                "enum": list(schemas),
                "description": "The one frame the plan reads. A plan always reads exactly one.",
            },
            "filters": {
                "type": "array",
                "description": "Conditions every row must meet, combined with AND.",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": column,
                        "op": {"type": "string", "enum": list(Op.__args__)},
                        "value": {
                            "anyOf": [scalar, {"type": "array", "items": scalar}],
                            "description": (
                                "A single value, or a list for 'in' and 'not_in'. "
                                "Dates are written YYYY-MM-DD."
                            ),
                        },
                    },
                    "required": ["column", "op", "value"],
                },
            },
            "group_by": {
                "type": "array",
                "items": column,
                "maxItems": MAX_GROUP_BY,
                "description": "Columns to group by. Needs an aggregate.",
            },
            "aggregate": {
                "type": "object",
                "description": "What to compute. Leave out to list rows instead.",
                "properties": {
                    "function": {"type": "string", "enum": list(Function.__args__)},
                    "column": {
                        **column,
                        "description": "The column to aggregate. Leave out for count, which counts rows.",
                    },
                },
                "required": ["function"],
            },
            "columns": {
                "type": "array",
                "items": column,
                "description": "For a row listing only: which columns to show.",
            },
            "sort_by": {
                "type": "string",
                "enum": [RESULT, *columns],
                "description": f"Column to sort by. On a grouped aggregate, '{RESULT}' sorts by the computed value.",
            },
            "descending": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": ROW_CAP},
            "decline_reason": {
                "type": "string",
                "description": (
                    "Why the question can't be answered from these frames, when it can't. "
                    "Leave every other field out when you set this."
                ),
            },
            "refines_previous": {
                "type": "boolean",
                "description": (
                    "True when this plan is the previous plan in the conversation "
                    "with only the change the question asks for."
                ),
            },
        },
    }


__all__ = [
    "ROW_CAP",
    "RESULT",
    "Aggregate",
    "Column",
    "Filter",
    "FrameSchema",
    "PlanRejection",
    "QueryPlan",
    "QueryResult",
    "describe_change",
    "describe_frames",
    "run",
    "tool_schema",
]
