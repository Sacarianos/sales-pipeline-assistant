"""Issue 07: risk as best-case coverage, with the invented-threshold
disclosure and the reps-who-clear-quota facts.

Per the parent spec's testing decisions, these go in through the primary
seam — a question string plus the loaded data — and assert on what reaches
the screen. Reference values are independently computed from the CSVs and
match the parent spec's pinned figures.
"""

from __future__ import annotations

from acme.domain import Answered, Refused
from acme.pipeline import ask
from tests.test_llm_router_and_refusals import StubRouterClient


def _risk_input(**overrides) -> dict:
    base = dict(
        metric="risk",
        grouping="overall",
        period="Q2-2026",
        restated="Reading this as risk across the whole organization for Q2-2026.",
    )
    base.update(overrides)
    return base


def test_eight_of_ten_reps_are_below_100_percent_best_case(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "risk"
    assert answer.intent.grouping == "overall"
    assert answer.facts["at_risk_count"].value == 8
    assert answer.facts["clear_count"].value == 2
    assert len(answer.table) == 10
    clears = set(answer.table.loc[answer.table["best_case_pct"] >= 100, "rep"])
    assert clears == {"Marcus Rivera", "James Okafor"}


def test_organization_best_case_against_quota_and_shortfall(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    assert answer.facts["best_case"].value == 5_716_000
    assert answer.facts["quota"].value == 6_200_000
    assert answer.facts["shortfall"].value == 484_000


def test_closed_won_and_open_pipeline_both_filtered_by_period_membership(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    assert set(answer.source_rows["period"]) == {"Q2-2026"}


def test_reps_below_100_percent_never_named_in_a_fact_label(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    # Tom Bradley is the closest rep below the threshold (98.7 percent) per
    # the parent spec's reference values, so his name is the sharpest check
    # that a below-threshold rep gets no fact at all.
    labels = " ".join(fact.label for fact in answer.facts.values())
    assert "Tom Bradley" not in labels
    assert "Tom Bradley" in answer.table["rep"].tolist()
    assert "Tom Bradley" in answer.source_rows["rep_name"].tolist()


def test_single_rep_grouping_answers_for_a_rep_clearing_quota(data):
    answer = ask("is Marcus Rivera at risk of missing quota this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.intent.grouping == "rep"
    assert answer.intent.rep == "Marcus Rivera"
    assert answer.facts["best_case"].value == 1_125_000
    assert answer.facts["quota"].value == 850_000
    assert round(answer.facts["best_case_pct"].value, 1) == 132.4


def test_invented_threshold_flag_names_it_as_ours_not_acmes(data):
    answer = ask("which reps are at risk of missing Q2", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "invented_rule")
    assert "not a Acme standard" in flag.detail
    # Pace was rejected as the rule, and no fact is computed from it.
    assert "pace" in flag.detail.lower()
    assert "pace" not in " ".join(fact.label.lower() for fact in answer.facts.values())


def test_risk_refuses_at_segment_grouping(data):
    client = StubRouterClient(tool_input=_risk_input(grouping="segment", segment="Enterprise"))
    answer = ask("how is Enterprise doing on risk this quarter", data, client)

    assert isinstance(answer, Refused)
    assert "risk" in answer.reason
    assert "segment" in answer.reason


def test_risk_refuses_for_a_period_that_already_closed(data):
    client = StubRouterClient(tool_input=_risk_input(period="Q1-2026"))
    answer = ask("who was at risk of missing Q1", data, client)

    assert isinstance(answer, Refused)
    assert "risk" in answer.reason
    assert "Q1-2026" in answer.reason
