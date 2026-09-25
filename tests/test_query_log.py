"""Issue 04: the query log.

Every exploratory attempt appends one record, so V3's promote-to-metric path
has a history to promote from. Asserted through the primary seam, with the
log injected and pointed at a temporary file.
"""

from __future__ import annotations

import pytest

from acme import query_plan
from acme.pipeline import ask
from acme.query_log import QueryLog
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input
from tests.test_llm_router_and_refusals import StubRouterClient

TOTAL = {"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}}
LOSS_REASONS = {
    "frame": "deals_q2",
    "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}],
    "group_by": ["loss_reason"],
    "aggregate": {"function": "count"},
}


@pytest.fixture
def log(tmp_path):
    return QueryLog(tmp_path / "query_log.jsonl")


def _ask(question, data, log, plan_input=None):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=plan_input)
    return ask(question, data, client, log=log)


def test_an_answered_attempt_records_the_question_plan_and_counts(data, log):
    _ask("why are we losing deals", data, log, LOSS_REASONS)

    [record] = log.records()
    assert record.question == "why are we losing deals"
    assert record.outcome == "answered"
    assert record.plan == LOSS_REASONS
    assert record.reason is None
    assert record.matched_rows == int((data.deals("Q2")["stage"] == "Closed Lost").sum())
    assert record.row_count == 7
    assert record.logged_at


def test_a_decline_is_recorded_with_its_reason_and_no_plan(data, log):
    _ask("what did our Slack sentiment look like", data, log, {"decline_reason": "no column covers Slack sentiment"})

    [record] = log.records()
    assert record.outcome == "declined"
    assert record.plan is None
    assert record.reason == "no column covers Slack sentiment"


def test_a_rejected_plan_is_recorded_with_the_plan_and_the_reason(data, log):
    plan = {"frame": "deals_q2", "group_by": ["region"], "aggregate": {"function": "count"}}
    _ask("which part of the country has the most pipeline", data, log, plan)

    [record] = log.records()
    assert record.outcome == "rejected"
    assert record.plan == plan
    assert "'region' is withheld" in record.reason


def test_a_malformed_plan_refuses_and_is_recorded_as_rejected(data, log):
    """The generator can return a plan the schema doesn't allow, here an
    aggregate function that doesn't exist. That has to refuse, not crash."""
    plan = {"frame": "deals_q2", "aggregate": {"function": "average", "column": "deal_value"}}
    answer = _ask("what's the average deal", data, log, plan)

    assert answer.kind == "refused"
    [record] = log.records()
    assert record.outcome == "rejected"
    assert record.plan == plan


def test_a_plan_that_fails_while_running_is_recorded_as_failed(data, log, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(query_plan, "_execute", explode)
    _ask("what's our total pipeline", data, log, TOTAL)

    [record] = log.records()
    assert record.outcome == "failed"
    assert record.plan == TOTAL
    assert "boom" in record.reason


def test_a_generator_call_that_fails_is_recorded_as_unavailable(data, log):
    _ask("why are we losing deals", data, log, plan_input=None)

    [record] = log.records()
    assert record.outcome == "unavailable"
    assert record.plan is None


def test_metric_answers_and_refused_topics_append_nothing(data, log):
    metric_client = StubRouterClient(
        tool_input=dict(
            metric="attainment",
            grouping="overall",
            period="Q2-2026",
            restated="Reading this as attainment across the whole organization for Q2-2026.",
        )
    )
    ask("how are we tracking this quarter", data, metric_client, log=log)
    _ask("how is the West region doing", data, log, TOTAL)
    ask("why are we losing deals", data, None, log=log)

    assert log.records() == []


def test_the_log_is_append_only(data, log):
    _ask("why are we losing deals", data, log, LOSS_REASONS)
    first_line = log.path.read_text(encoding="utf-8")

    _ask("what's our total pipeline", data, log, TOTAL)
    contents = log.path.read_text(encoding="utf-8")

    assert contents.startswith(first_line)
    assert len(contents.splitlines()) == 2


def test_the_log_survives_a_restart(data, log):
    _ask("why are we losing deals", data, log, LOSS_REASONS)
    _ask("what's our total pipeline", data, log, TOTAL)

    reopened = QueryLog(log.path)
    assert [r.question for r in reopened.records()] == [
        "why are we losing deals",
        "what's our total pipeline",
    ]
