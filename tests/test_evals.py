"""The eval harness scores what it's supposed to. Driven by stub clients, so
these run offline; the harness itself is what runs against real models."""

from __future__ import annotations

import io

from evals.cases import CASES, Case
from evals.run import changes, main, pass_rates, run_case
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input
from tests.test_llm_router_and_refusals import StubRouterClient

ATTAINMENT = dict(metric="attainment", grouping="overall", period="Q2-2026", restated="Reading this as attainment.")


def _case(case_id: str) -> Case:
    return next(case for case in CASES if case.id == case_id)


def test_a_correct_routing_passes(data, tmp_path):
    result = run_case(_case("attainment-overall"), 1, data, StubRouterClient(tool_input=ATTAINMENT), tmp_path)
    assert result.passed, result.failures
    assert result.lane == "metric"


def test_a_misrouted_metric_question_fails_with_the_difference(data, tmp_path):
    client = StubRouterClient(tool_input={**ATTAINMENT, "grouping": "segment", "segment": "SMB"})
    result = run_case(_case("attainment-segment"), 1, data, client, tmp_path)
    assert not result.passed
    assert "segment was 'SMB', expected 'Enterprise'" in result.failures


def test_an_exploratory_answer_is_scored_on_its_figures_not_its_plan(data, tmp_path):
    """Lost deals filtered on `stage` or on `is_lost` compute the same thing,
    so both pass."""
    for lost in ({"column": "stage", "op": "eq", "value": "Closed Lost"}, {"column": "is_lost", "op": "eq", "value": True}):
        client = FallbackStubClient(
            router_input=_unsupported_input(),
            plan_input={"frame": "deals_q2", "filters": [lost], "group_by": ["loss_reason"], "aggregate": {"function": "count"}},
        )
        result = run_case(_case("loss-reasons"), 1, data, client, tmp_path)
        assert result.passed, result.failures
        assert result.plan["filters"] == [lost]


def test_a_wrong_exploratory_figure_fails(data, tmp_path):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "group_by": ["loss_reason"], "aggregate": {"function": "count"}},
    )
    result = run_case(_case("loss-reasons"), 1, data, client, tmp_path)
    assert not result.passed
    assert result.failures[0].startswith("table was")


def test_this_quarter_accepts_only_the_period_reading(data, tmp_path):
    whole_snapshot = {"frame": "deals_q2", "filters": [{"column": "is_won", "op": "eq", "value": True}], "aggregate": {"function": "max", "column": "deal_value"}}
    this_quarter = {**whole_snapshot, "filters": [*whole_snapshot["filters"], {"column": "period", "op": "eq", "value": "Q2-2026"}]}
    case = _case("biggest-win-this-quarter")
    results = {
        name: run_case(case, 1, data, FallbackStubClient(router_input=_unsupported_input(), plan_input=plan), tmp_path)
        for name, plan in (("whole", whole_snapshot), ("quarter", this_quarter))
    }
    q2 = data.deals("Q2")
    if q2[q2["is_won"]]["deal_value"].max() != q2[q2["is_won"] & (q2["period"] == "Q2-2026")]["deal_value"].max():
        assert not results["whole"].passed
    assert results["quarter"].passed, results["quarter"].failures


def test_an_answer_to_a_question_that_should_refuse_fails(data, tmp_path):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "group_by": ["segment"], "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    result = run_case(_case("geography-paraphrase"), 1, data, client, tmp_path)
    assert result.failures == ("landed in exploratory, expected refused",)


def test_a_refused_topic_passes_only_without_a_generator_call(data, tmp_path):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input={"frame": "deals_q2"})
    result = run_case(_case("region-word"), 1, data, client, tmp_path)
    assert result.passed, result.failures
    assert result.calls == ()


def test_an_offline_fallback_counts_as_a_failure(data, tmp_path):
    client = StubRouterClient(raises=ConnectionError("down"))
    result = run_case(_case("attainment-overall"), 1, data, client, tmp_path)
    assert "the router fell back to offline, so a model call failed" in result.failures


def test_calls_and_tokens_are_recorded(data, tmp_path):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "filters": [{"column": "stage", "op": "eq", "value": "Negotiation"}], "aggregate": {"function": "count"}},
        narrator_text="There are 13 deals in negotiation.",
    )
    result = run_case(_case("negotiation-count"), 1, data, client, tmp_path)
    assert result.calls == ("route_question", "plan_query", "narrate")
    assert result.narration in ("narrator", "blocked")


def test_changes_lists_what_moved():
    assert changes({"a": 1.0, "b": 0.0, "c": 1.0}, {"a": 1.0, "b": 1.0, "d": 0.5}) == [
        "improved  b: 0% -> 100%",
        "new       d: 50%",
        "gone      c",
    ]


def test_pass_rates_average_repeats(data, tmp_path):
    client = StubRouterClient(tool_input=ATTAINMENT)
    good = run_case(_case("attainment-overall"), 1, data, client, tmp_path)
    bad = run_case(_case("attainment-q1"), 1, data, client, tmp_path)
    assert pass_rates([good, good]) == {"attainment-overall": 1.0}
    assert pass_rates([bad]) == {"attainment-q1": 0.0}


def test_every_case_id_is_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_main_saves_results_and_compares_with_the_last_run(data, tmp_path):
    out = io.StringIO()
    factory = lambda: StubRouterClient(tool_input=ATTAINMENT)  # noqa: E731
    assert main(["--only", "attainment-overall", "--workers", "1"], out=out, client_factory=factory, results_dir=tmp_path) == 0
    assert len(list(tmp_path.glob("*.json"))) == 1

    out = io.StringIO()
    main(["--only", "attainment-overall", "--workers", "1"], out=out, client_factory=factory, results_dir=tmp_path)
    assert "No change since the last run." in out.getvalue()
