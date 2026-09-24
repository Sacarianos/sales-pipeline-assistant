"""Conversation memory: earlier turns reach the router and the generator as
readings, never as answers. See docs/specs/conversation-memory.md."""

from __future__ import annotations

import json
from pathlib import Path

from acme import fallback
from acme.conversation import MEMORY_TURNS, Turn, remember, turn
from acme.domain import Answered, Intent, Refused, Unit
from acme.pipeline import ask
from acme.query_log import QueryLog
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input
from tests.test_llm_router_and_refusals import StubRouterClient

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

ENTERPRISE = dict(
    metric="attainment", grouping="segment", segment="Enterprise", period="Q2-2026",
    restated="Reading this as attainment for the Enterprise segment for Q2-2026.",
)
LOSS_REASONS = {
    "frame": "deals_q2",
    "filters": [{"column": "is_lost", "op": "eq", "value": True}],
    "group_by": ["loss_reason"],
    "aggregate": {"function": "count"},
}


def _metric_turn(data) -> tuple[Turn, Answered]:
    answer = ask("how is the Enterprise segment doing", data, StubRouterClient(tool_input=ENTERPRISE))
    assert isinstance(answer, Answered)
    return turn("how is the Enterprise segment doing", answer), answer


def _exploratory_turn(data) -> tuple[Turn, Answered]:
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS)
    answer = ask("why are we losing deals", data, client)
    assert isinstance(answer, Answered)
    return turn("why are we losing deals", answer), answer


def _user_message(call: dict) -> str:
    return json.dumps(call["messages"])


def _figures(answer: Answered) -> list[str]:
    return [fact.formatted() for fact in answer.facts.values() if fact.unit is Unit.CURRENCY and fact.value >= 1000]


# --- what a turn remembers ---------------------------------------------------


def test_a_metric_turn_remembers_its_reading_and_nothing_it_computed(data):
    remembered, answer = _metric_turn(data)
    assert remembered.lane == "metric"
    assert remembered.intent["segment"] == "Enterprise"
    assert remembered.plan is None
    text = json.dumps(remembered.__dict__)
    for figure in _figures(answer):
        assert figure not in text


def test_an_exploratory_turn_remembers_its_plan_and_description(data):
    remembered, answer = _exploratory_turn(data)
    assert remembered.lane == "exploratory"
    assert remembered.plan == LOSS_REASONS | {"frame": "deals_q2"}
    assert remembered.restated == answer.restated


def test_a_refused_turn_remembers_only_its_question_and_reading(data):
    answer = ask("how is the West region doing", data)
    remembered = turn("how is the West region doing", answer)
    assert remembered.lane == "refused"
    assert remembered.plan is None


def test_memory_keeps_the_last_three_turns(data):
    remembered, _ = _metric_turn(data)
    turns = [Turn(question=f"q{i}", lane="metric", restated="", intent=None, plan=None) for i in range(5)]
    assert [t.question for t in remember(turns)] == ["q2", "q3", "q4"]
    assert MEMORY_TURNS == 3


# --- what reaches the models -------------------------------------------------


def test_the_router_sees_the_earlier_question_and_reading(data):
    earlier, _ = _metric_turn(data)
    client = StubRouterClient(tool_input=ENTERPRISE | {"segment": "SMB", "follows_up": True})
    ask("what about SMB", data, client, history=(earlier,))

    message = _user_message(client.calls[0])
    assert "how is the Enterprise segment doing" in message
    assert "Enterprise" in message
    assert "what about SMB" in message


def test_no_figure_from_an_earlier_answer_reaches_any_model(data):
    earlier, answer = _metric_turn(data)
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS)
    ask("why are we losing deals there", data, client, history=(earlier,))

    everything = " ".join(json.dumps(call.get("messages")) + str(call.get("system")) for call in client.calls)
    for figure in _figures(answer):
        assert figure not in everything


def test_the_narrator_is_not_given_earlier_turns(data):
    earlier, _ = _metric_turn(data)
    client = FallbackStubClient(
        router_input=_unsupported_input(), plan_input=LOSS_REASONS, narrator_text="Losses by reason.",
    )
    ask("why are we losing deals", data, client, history=(earlier,))
    narrator_call = next(call for call in client.calls if not call.get("tools"))
    assert "how is the Enterprise segment doing" not in _user_message(narrator_call)


def test_the_router_prompt_explains_follow_ups(data):
    from acme import router
    from acme.catalog import build_catalog

    prompt = router._system_prompt(build_catalog(data))
    assert "follows_up" in prompt
    assert "Following on from" in prompt
    assert "follows_up" in Intent.model_json_schema()["properties"]


def test_the_offline_router_ignores_memory(data):
    earlier, _ = _metric_turn(data)
    alone = ask("how are we tracking this quarter", data)
    with_memory = ask("how are we tracking this quarter", data, history=(earlier,))
    assert with_memory.intent == alone.intent


def test_a_follow_up_about_a_refused_topic_still_refuses_before_any_model(data):
    earlier, _ = _metric_turn(data)
    client = StubRouterClient(tool_input=ENTERPRISE)
    answer = ask("what about the West", data, client, history=(earlier,))
    assert isinstance(answer, Refused)
    assert client.calls == []


# --- exploratory refinements -------------------------------------------------


def _follow_up_input() -> dict:
    return _unsupported_input() | {"follows_up": True}


def test_the_generator_sees_the_previous_plan(data):
    earlier, _ = _exploratory_turn(data)
    client = FallbackStubClient(router_input=_follow_up_input(), plan_input=LOSS_REASONS)
    ask("just for Enterprise", data, client, history=(earlier,))

    message = _user_message(client.generator_call())
    assert "loss_reason" in message
    assert "just for Enterprise" in message


def test_a_refined_plan_says_what_changed(data):
    earlier, _ = _exploratory_turn(data)
    refined = LOSS_REASONS | {
        "filters": [*LOSS_REASONS["filters"], {"column": "segment", "op": "eq", "value": "Enterprise"}],
        "refines_previous": True,
    }
    client = FallbackStubClient(router_input=_follow_up_input(), plan_input=refined)
    answer = ask("just for Enterprise", data, client, history=(earlier,))

    assert isinstance(answer, Answered)
    assert answer.change_from_previous == "Changed from your last query: added segment is Enterprise."
    assert set(answer.source_rows["segment"]) == {"Enterprise"}


def test_a_standalone_question_never_shows_the_generator_earlier_turns(data):
    """Found by the evals: "why are we losing deals" after an Enterprise
    question came back filtered to Enterprise once in three runs. The router
    decides whether a question follows on, and the generator only sees
    earlier turns when it does."""
    earlier, _ = _metric_turn(data)
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS)
    ask("why are we losing deals", data, client, history=(earlier,))

    message = _user_message(client.generator_call())
    assert "Enterprise" not in message
    assert "Earlier in this conversation" not in message


def test_the_router_is_told_a_comparison_needs_its_earlier_period(data):
    """Found by the evals: a comparison was restated "against Q1-2026" with
    comparison_period left empty, so validation refused it."""
    from acme import router
    from acme.catalog import build_catalog

    assert "always set comparison_period" in router._system_prompt(build_catalog(data))


def test_a_plan_that_refines_nothing_says_nothing_changed(data):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS | {"refines_previous": True})
    answer = ask("why are we losing deals", data, client)
    assert answer.change_from_previous == ""


def test_a_follow_up_is_logged_as_one(data, tmp_path):
    earlier, _ = _exploratory_turn(data)
    log = QueryLog(tmp_path / "log.jsonl")
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS | {"refines_previous": True})
    ask("just for Enterprise", data, client, history=(earlier,), log=log)
    ask("why are we losing deals", data, FallbackStubClient(router_input=_unsupported_input(), plan_input=LOSS_REASONS), log=log)

    assert [r.follows_up for r in log.records()] == [True, False]


def test_a_follow_up_counts_toward_promotion_but_is_never_an_example(data, tmp_path):
    from acme.promotion import find_candidates
    from acme.query_log import LogRecord

    records = [
        LogRecord(question="why are we losing deals", outcome="answered", plan=LOSS_REASONS),
        LogRecord(question="and now?", outcome="answered", plan=LOSS_REASONS, follows_up=True),
    ]
    [candidate] = find_candidates(records, data)
    assert candidate.count == 2
    assert candidate.questions == ("why are we losing deals",)


# --- the app -----------------------------------------------------------------


def test_a_follow_up_shows_what_it_carried_over_above_the_answer():
    """The chat shows no restatement for a standalone answer, only the trace
    panel does. A follow-up is different: what it carried over is the one
    thing the reader has to check, so its restatement shows in the chat,
    ahead of the prose."""
    caption = APP_SOURCE.index("if answer.intent is not None and answer.intent.follows_up:")
    prose = APP_SOURCE.index("st.write_stream(_typewriter(answer.prose))")
    assert caption < prose


def test_the_app_passes_memory_and_can_start_a_new_conversation():
    assert "history=memory" in APP_SOURCE
    assert '"New conversation"' in APP_SOURCE
    assert "st.session_state.history = []" in APP_SOURCE
