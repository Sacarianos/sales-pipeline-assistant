"""The structured query plan the fallback lane runs instead of generated code.

This is a direct seam, the way the reconciler's change log was in V1. It is
the highest-risk code in the lane, so the rejection tests below try to get a
plan past the checker that should never run, and the equivalence tests pin
the pandas the plan displays to the pandas that actually ran.
"""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from acme.query_plan import (
    ROW_CAP,
    PlanRejection,
    QueryPlan,
    QueryResult,
    describe_frames,
    run,
    tool_schema,
)

FRAMES = {
    "deals": pd.DataFrame(
        {
            "deal_id": [f"OPP-{i}" for i in range(20)],
            "segment": ["Enterprise", "SMB", "Mid-Market", "Enterprise"] * 5,
            "stage": ["Closed Won", "Closed Lost", "Proposal", "Closed Lost"] * 5,
            "region": ["West", "Central", "West", "Northeast"] * 5,
            "deal_value": [float(1000 * (i + 1)) for i in range(20)],
            "is_won": [True, False, False, False] * 5,
            "close_date": [datetime.date(2026, 4, 1) + datetime.timedelta(days=i) for i in range(20)],
        }
    ),
    "big": pd.DataFrame({"n": [float(i) for i in range(ROW_CAP + 50)]}),
}
SCHEMAS = describe_frames(FRAMES, hidden_columns=frozenset({"region"}))


def _plan(**fields) -> QueryPlan:
    return QueryPlan(**fields)


def _ok(plan: QueryPlan) -> QueryResult:
    outcome = run(plan, FRAMES, SCHEMAS)
    assert isinstance(outcome, QueryResult), outcome
    return outcome


def test_a_filtered_sum_returns_a_scalar_and_the_matched_row_count():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "stage", "op": "eq", "value": "Closed Lost"}],
            aggregate={"function": "sum", "column": "deal_value"},
        )
    )
    deals = FRAMES["deals"]
    expected = deals[deals["stage"] == "Closed Lost"]["deal_value"].sum()
    assert outcome.value == expected
    assert outcome.matched_rows == 10


def test_a_grouped_count_sorts_and_limits():
    outcome = _ok(
        _plan(
            frame="deals",
            group_by=["stage"],
            aggregate={"function": "count"},
            sort_by="result",
            descending=True,
            limit=2,
        )
    )
    assert list(outcome.value.columns) == ["stage", "count"]
    assert outcome.value.iloc[0].to_dict() == {"stage": "Closed Lost", "count": 10}
    assert len(outcome.value) == 2


def test_a_row_listing_returns_only_the_requested_columns():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "deal_value", "op": "gte", "value": 18000}],
            columns=["deal_id", "deal_value"],
            sort_by="deal_value",
            descending=True,
        )
    )
    assert list(outcome.value.columns) == ["deal_id", "deal_value"]
    assert outcome.value["deal_value"].tolist() == [20000.0, 19000.0, 18000.0]


def test_a_row_listing_with_no_columns_named_still_leaves_hidden_columns_out():
    outcome = _ok(_plan(frame="deals", limit=3))
    assert "region" not in outcome.value.columns
    assert "deal_value" in outcome.value.columns


def test_an_aggregate_over_no_matching_rows_reports_no_value_rather_than_nan():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "deal_value", "op": "gt", "value": 10_000_000}],
            aggregate={"function": "mean", "column": "deal_value"},
        )
    )
    assert outcome.value is None
    assert outcome.matched_rows == 0


def test_a_result_past_the_row_cap_truncates_and_reports_the_full_count():
    outcome = _ok(_plan(frame="big"))
    assert outcome.truncated is True
    assert outcome.row_count == ROW_CAP + 50
    assert len(outcome.value) == ROW_CAP


EQUIVALENCE_PLANS = [
    dict(frame="deals", aggregate={"function": "sum", "column": "deal_value"}),
    dict(frame="deals", aggregate={"function": "count"}),
    dict(frame="deals", aggregate={"function": "nunique", "column": "segment"}),
    dict(
        frame="deals",
        filters=[
            {"column": "stage", "op": "in", "value": ["Closed Won", "Closed Lost"]},
            {"column": "close_date", "op": "lt", "value": "2026-04-10"},
        ],
        group_by=["segment", "stage"],
        aggregate={"function": "mean", "column": "deal_value"},
        sort_by="result",
        descending=False,
    ),
    dict(
        frame="deals",
        filters=[
            {"column": "is_won", "op": "eq", "value": False},
            {"column": "segment", "op": "not_in", "value": ["SMB"]},
        ],
        columns=["deal_id", "segment", "deal_value"],
        sort_by="deal_value",
        limit=4,
    ),
    dict(frame="deals", filters=[{"column": "deal_id", "op": "eq", "value": "x') | (deals['a'] > 0"}]),
]


@pytest.mark.parametrize("fields", EQUIVALENCE_PLANS)
def test_the_displayed_pandas_reproduces_the_result_exactly(fields):
    """The code on screen is what an analyst pastes into a notebook, so it
    has to produce the same answer the lane published. The last plan puts a
    code fragment in a filter value: it renders as a quoted string and
    matches nothing, the same as it did when the plan ran."""
    outcome = _ok(_plan(**fields))
    reproduced = eval(outcome.code, {"datetime": datetime, **FRAMES})  # noqa: S307
    if isinstance(outcome.value, pd.DataFrame):
        pd.testing.assert_frame_equal(
            reproduced.reset_index(drop=True), outcome.value.reset_index(drop=True)
        )
    else:
        assert reproduced == outcome.value


def test_the_description_reads_as_plain_english():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "stage", "op": "eq", "value": "Closed Lost"}],
            group_by=["segment"],
            aggregate={"function": "sum", "column": "deal_value"},
            sort_by="result",
            limit=5,
        )
    )
    assert outcome.description == (
        "Total deal value across rows in the deals frame where stage is Closed Lost, "
        "grouped by segment, sorted by the result, highest first, top 5."
    )


@pytest.mark.parametrize(
    ("fields", "reason_fragment"),
    [
        (dict(), "must name a frame"),
        (dict(frame="deals_q1 + deals_q2"), "not one of the frames"),
        (dict(frame="deals", columns=["nope"]), "'nope' is not a column"),
        (dict(frame="deals", group_by=["region"], aggregate={"function": "count"}), "'region' is withheld"),
        (dict(frame="deals", filters=[{"column": "region", "op": "eq", "value": "West"}]), "'region' is withheld"),
        (dict(frame="deals", aggregate={"function": "sum", "column": "segment"}), "can't take sum"),
        (dict(frame="deals", aggregate={"function": "count", "column": "deal_value"}), "count counts rows"),
        (dict(frame="deals", aggregate={"function": "sum"}), "needs a column"),
        (dict(frame="deals", filters=[{"column": "segment", "op": "gt", "value": "SMB"}]), "can't compare"),
        (dict(frame="deals", filters=[{"column": "stage", "op": "eq", "value": "Closed-Lost"}]), "not a value"),
        (dict(frame="deals", filters=[{"column": "is_won", "op": "eq", "value": "yes"}]), "true or false"),
        (dict(frame="deals", filters=[{"column": "deal_value", "op": "gt", "value": "big"}]), "needs a number"),
        (dict(frame="deals", filters=[{"column": "close_date", "op": "gt", "value": "April"}]), "YYYY-MM-DD"),
        (dict(frame="deals", filters=[{"column": "segment", "op": "in", "value": "SMB"}]), "needs a list"),
        (dict(frame="deals", filters=[{"column": "segment", "op": "eq", "value": ["SMB"]}]), "single value"),
        (dict(frame="deals", group_by=["deal_value"], aggregate={"function": "count"}), "can't group by"),
        (dict(frame="deals", group_by=["segment", "stage", "is_won"], aggregate={"function": "count"}), "at most 2"),
        (dict(frame="deals", group_by=["segment"], aggregate={"function": "nunique", "column": "segment"}), "also grouped by"),
        (dict(frame="deals", group_by=["segment"]), "needs an aggregate"),
        (dict(frame="deals", columns=["deal_id"], aggregate={"function": "count"}), "columns only apply"),
        (dict(frame="deals", columns=["deal_id"], sort_by="deal_value"), "sort by"),
        (dict(frame="deals", aggregate={"function": "count"}, sort_by="result"), "single number"),
        (dict(frame="deals", limit=0), "limit"),
        (dict(frame="deals", limit=ROW_CAP + 1), "limit"),
    ],
)
def test_a_plan_outside_the_rules_is_rejected_before_anything_runs(fields, reason_fragment):
    outcome = run(_plan(**fields), FRAMES, SCHEMAS)
    assert isinstance(outcome, PlanRejection)
    assert reason_fragment in outcome.reason


def test_a_true_or_false_column_reads_naturally_in_the_description():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "is_won", "op": "eq", "value": False}],
            aggregate={"function": "count"},
        )
    )
    assert outcome.description == "Number of rows in the deals frame where the row is not won."


def test_the_tool_schema_enumerates_frames_and_columns_but_never_a_hidden_one():
    schema = tool_schema(SCHEMAS)
    assert schema["properties"]["frame"]["enum"] == ["deals", "big"]
    columns = schema["properties"]["filters"]["items"]["properties"]["column"]["enum"]
    assert "deal_value" in columns
    assert "region" not in columns


def test_the_tool_schema_has_no_field_that_takes_code():
    """A plan names one frame and a fixed set of operations. Nothing in it
    is ever handed to eval, so no string the model writes can execute."""
    schema = tool_schema(SCHEMAS)
    assert "expression" not in schema["properties"]
    assert schema["properties"]["frame"]["type"] == "string"


def test_a_result_carries_the_matched_rows_without_withheld_columns():
    outcome = _ok(
        _plan(
            frame="deals",
            filters=[{"column": "stage", "op": "eq", "value": "Closed Won"}],
            aggregate={"function": "count"},
        )
    )
    assert len(outcome.rows) == outcome.matched_rows == 5
    assert "region" not in outcome.rows.columns


def test_a_trusted_column_accepts_a_value_it_does_not_hold_and_matches_nothing():
    plan = _plan(
        frame="deals",
        filters=[{"column": "segment", "op": "eq", "value": "Public Sector"}],
        aggregate={"function": "count"},
    )
    assert isinstance(run(plan, FRAMES, SCHEMAS), PlanRejection)

    outcome = run(plan, FRAMES, SCHEMAS, trusted_columns=frozenset({"segment"}))
    assert isinstance(outcome, QueryResult)
    assert outcome.value == 0


def test_a_trusted_column_still_needs_text():
    plan = _plan(
        frame="deals",
        filters=[{"column": "segment", "op": "eq", "value": 3}],
        aggregate={"function": "count"},
    )
    outcome = run(plan, FRAMES, SCHEMAS, trusted_columns=frozenset({"segment"}))
    assert isinstance(outcome, PlanRejection)
    assert "needs text" in outcome.reason


def test_a_change_between_two_plans_reads_as_plain_english():
    from acme.query_plan import describe_change

    before = {"frame": "deals", "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}], "aggregate": {"function": "count"}}
    added = {**before, "filters": [*before["filters"], {"column": "segment", "op": "eq", "value": "SMB"}]}
    assert describe_change(before, added, SCHEMAS) == "Changed from your last query: added segment is SMB."

    regrouped = {**before, "group_by": ["segment"], "sort_by": "result"}
    assert describe_change(before, regrouped, SCHEMAS) == (
        "Changed from your last query: now grouped by segment, sorted by the result, highest first."
    )

    swapped = {**before, "filters": [{"column": "stage", "op": "eq", "value": "Closed Won"}]}
    assert describe_change(before, swapped, SCHEMAS) == (
        "Changed from your last query: added stage is Closed Won; removed stage is Closed Lost."
    )

    summed = {**before, "aggregate": {"function": "sum", "column": "deal_value"}}
    assert describe_change(before, summed, SCHEMAS) == "Changed from your last query: now computes total deal value."

    assert describe_change(before, before, SCHEMAS) == "Same query as your last one."


def test_a_listing_that_goes_back_to_every_column_says_so():
    """Found in review: a refinement from two named columns back to all of
    them showed every column but was described as the same query."""
    from acme.query_plan import describe_change

    narrow = {"frame": "deals", "columns": ["deal_id", "deal_value"]}
    wide = {"frame": "deals"}
    assert describe_change(narrow, wide, SCHEMAS) == "Changed from your last query: now showing every column."


def test_a_sort_direction_on_an_unsorted_plan_is_not_a_change():
    """Found in review: `descending` means nothing without `sort_by`, so a
    flip between two unsorted plans was reported as a change."""
    from acme.query_plan import describe_change

    before = {"frame": "deals", "aggregate": {"function": "count"}}
    after = {**before, "descending": False}
    assert describe_change(before, after, SCHEMAS) == "Same query as your last one."
