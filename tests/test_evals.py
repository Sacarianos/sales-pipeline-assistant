"""The eval harness scores what it's supposed to. Driven by stub clients, so
these run offline; the harness itself is what runs against real models."""

from __future__ import annotations

import io

from evals.cases import CASES, Case
from evals.run import main, run_case
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input
from tests.test_llm_router_and_refusals import StubRouterClient

ATTAINMENT = dict(metric="attainment", grouping="overall", period="Q2-2026", restated="Reading this as attainment.")


def _case(case_id: str) -> Case:
    return next(case for case in CASES if case.id == case_id)


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


def test_a_refused_topic_passes_only_without_a_generator_call(data, tmp_path):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input={"frame": "deals_q2"})
    result = run_case(_case("region-word"), 1, data, client, tmp_path)
    assert result.passed, result.failures
    assert result.calls == ()


def test_main_saves_results_and_compares_with_the_last_run(data, tmp_path):
    out = io.StringIO()
    factory = lambda: StubRouterClient(tool_input=ATTAINMENT)  # noqa: E731
    assert main(["--only", "attainment-overall", "--workers", "1"], out=out, client_factory=factory, results_dir=tmp_path) == 0
    assert len(list(tmp_path.glob("*.json"))) == 1

    out = io.StringIO()
    main(["--only", "attainment-overall", "--workers", "1"], out=out, client_factory=factory, results_dir=tmp_path)
    assert "No change since the last run." in out.getvalue()
