"""Issue 08: comparison at the same day of quarter, never the same calendar
date, with each side drawn from the snapshot that owns it.

Per the parent spec's testing decisions, these go in through the primary
seam - a question string plus the loaded data - and assert on what reaches
the screen. Reference values are independently computed from the CSVs and
match the parent spec's pinned figures.
"""

from __future__ import annotations

from acme.domain import Answered, Refused
from acme.pipeline import ask
from tests.test_llm_router_and_refusals import StubRouterClient


def _comparison_input(**overrides) -> dict:
    base = dict(
        metric="comparison",
        grouping="overall",
        period="Q2-2026",
        comparison_period="Q1-2026",
        restated=(
            "Reading this as comparison across the whole organization for "
            "Q2-2026 against the same day of quarter in Q1-2026."
        ),
    )
    base.update(overrides)
    return base


def test_q2_versus_same_point_in_q1_headline_case(data):
    answer = ask(
        "how does Q2 attainment compare to where we were at the same point in Q1",
        data,
    )

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "comparison"
    assert answer.intent.period == "Q2-2026"
    assert answer.intent.comparison_period == "Q1-2026"
    assert round(answer.facts["attainment_pct"].value, 1) == 8.4
    assert round(answer.facts["comparison_attainment_pct"].value, 1) == 21.3
    assert answer.facts["comparison_closed_won"].value == 1_260_000
    assert answer.facts["comparison_won_deal_count"].value == 10


def test_a_segment_comparison_scopes_both_sides_to_that_segment(data):
    answer = ask("how is Enterprise attainment in Q2 compared to the same point in Q1", data)

    assert isinstance(answer, Answered)
    assert answer.intent.segment == "Enterprise"
    # The Q2 side matches the Enterprise attainment answer, and the Q1 side is
    # the 4 Enterprise deals won by February 1 against a 3,500,000 quota.
    assert answer.facts["closed_won"].value == 165_000
    assert answer.facts["comparison_closed_won"].value == 725_000
    assert round(answer.facts["comparison_attainment_pct"].value, 1) == 20.7


def test_gap_is_its_own_precomputed_fact(data):
    answer = ask(
        "how does Q2 attainment compare to where we were at the same point in Q1",
        data,
    )

    assert isinstance(answer, Answered)
    expected = abs(
        answer.facts["comparison_attainment_pct"].value
        - answer.facts["attainment_pct"].value
    )
    assert answer.facts["gap_pct"].value == expected
    assert round(answer.facts["gap_pct"].value, 0) == 13


def test_q1_side_reads_from_the_q1_snapshot_and_q2_side_from_the_q2_snapshot(data):
    answer = ask(
        "how does Q2 attainment compare to where we were at the same point in Q1",
        data,
    )

    assert isinstance(answer, Answered)
    assert answer.filters["current snapshot"] == "Q2 snapshot"
    assert "Q1 snapshot" in answer.filters["comparison snapshot"]
    assert "not restated" in answer.filters["comparison snapshot"]
    q1_rows = answer.source_rows[answer.source_rows["period"] == "Q1-2026"]
    q2_rows = answer.source_rows[answer.source_rows["period"] == "Q2-2026"]
    assert not q1_rows.empty
    assert not q2_rows.empty


def test_backloading_flag_reports_share_of_q1_eventual_total_landed_by_cutoff(data):
    answer = ask(
        "how does Q2 attainment compare to where we were at the same point in Q1",
        data,
    )

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "backloading")
    assert "1,260,000" in flag.detail
    assert "6,041,000" in flag.detail
    assert "Q1-2026 finished strong from a slow start" in flag.detail


def test_comparison_refuses_at_rep_grouping(data):
    client = StubRouterClient(
        tool_input=_comparison_input(grouping="rep", rep="Marcus Rivera")
    )
    answer = ask("how does Marcus Rivera compare to Q1", data, client)

    assert isinstance(answer, Refused)
    assert "comparison" in answer.reason
    assert "rep" in answer.reason


def test_comparison_without_a_target_period_is_refused(data):
    client = StubRouterClient(tool_input=_comparison_input(comparison_period=None))
    answer = ask("how does Q2 compare", data, client)

    assert isinstance(answer, Refused)
    assert "target" in answer.reason.lower()


def test_comparison_target_outside_the_catalog_is_refused(data):
    client = StubRouterClient(
        tool_input=_comparison_input(comparison_period="Q3-2026")
    )
    answer = ask("how does Q2 compare to Q3", data, client)

    assert isinstance(answer, Refused)
    assert "Q3-2026" in answer.reason
