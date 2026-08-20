"""Issue 03: the Anthropic tool-use router, catalog-driven refusals, and the
offline fallback.

Per the parent spec's testing decisions, these tests go in through the
primary seam - `ask(question, data, client)` - and assert on what reaches the
screen. `client` is a stub shaped like `anthropic.Anthropic`, since that is
what makes the online router testable without a network call.
"""

from __future__ import annotations

from acme.catalog import build_catalog
from acme.domain import Answered, Intent, Refused
from acme.pipeline import ask


class _ToolUseBlock:
    def __init__(self, input: dict):
        self.type = "tool_use"
        self.input = input


class _Message:
    def __init__(self, content):
        self.content = content


class _Messages:
    def __init__(self, outer: "StubRouterClient"):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        if self._outer.raises is not None:
            raise self._outer.raises
        return _Message([_ToolUseBlock(self._outer.tool_input)])


class StubRouterClient:
    """A duck-typed stand-in for `anthropic.Anthropic`.

    Returns a fixed tool-call input regardless of the question, so a test
    controls exactly what the router "decided" without a real model call, or
    raises to simulate the API being unreachable.
    """

    def __init__(self, tool_input: dict | None = None, raises: Exception | None = None):
        self.tool_input = tool_input
        self.raises = raises
        self.calls: list[dict] = []
        self.messages = _Messages(self)


def _attainment_input(**overrides) -> dict:
    base = dict(
        metric="attainment",
        grouping="overall",
        period="Q2-2026",
        restated="Reading this as attainment across the whole organization for Q2-2026.",
    )
    base.update(overrides)
    return base


def test_routing_forces_tool_choice_to_the_single_query_tool(data):
    # The client also fields the narrator's call once routing succeeds, per
    # ADR/issue 04 - "the model is used exactly twice" - so this checks the
    # router's own call (the first one) rather than the full call count.
    client = StubRouterClient(tool_input=_attainment_input())
    ask("how are we tracking this quarter", data, client)

    call = client.calls[0]
    assert len(call["tools"]) == 1
    tool_name = call["tools"][0]["name"]
    assert call["tool_choice"] == {"type": "tool", "name": tool_name}


def test_intent_carries_every_field_the_router_is_asked_to_fill():
    fields = Intent.model_fields
    for name in (
        "metric", "grouping", "period", "comparison_period",
        "segment", "rep", "manager", "restated", "unsupported_reason",
    ):
        assert name in fields


def test_router_prompt_is_built_from_the_catalog(data):
    catalog = build_catalog(data)
    client = StubRouterClient(tool_input=_attainment_input())
    ask("how are we tracking this quarter", data, client)

    system_prompt = client.calls[0]["system"]
    spec = catalog.metric("attainment")
    assert spec.name in system_prompt
    assert spec.description in system_prompt
    for example in spec.examples:
        assert example in system_prompt
    for rep in catalog.reps:
        assert rep in system_prompt


def test_no_data_row_reaches_the_router_prompt(data):
    client = StubRouterClient(tool_input=_attainment_input())
    ask("how are we tracking this quarter", data, client)

    call = client.calls[0]
    prompt_text = call["system"] + repr(call["tools"])
    q2 = data.deals("Q2")
    # Account names and deal IDs are data rows; catalog-derived rep/segment
    # names are not. None of the former may appear anywhere in what the
    # router was shown.
    for account in q2["account_name"].unique():
        assert account not in prompt_text
    for deal_id in q2["deal_id"].unique():
        assert deal_id not in prompt_text


def test_west_region_refuses_naming_both_definitions_and_the_computed_count(data):
    answer = ask("how is the West region doing this quarter", data)

    assert isinstance(answer, Refused)
    assert str(data.region_mismatch_count) in answer.reason
    assert str(data.region_deal_count) in answer.reason
    assert "deal" in answer.reason.lower()
    assert "rep" in answer.reason.lower()


def test_region_refusal_short_circuits_before_the_model_is_asked(data):
    """`Intent` has no region field, so a model asked about region has only
    one wrong move available: substituting the nearest segment or rep. The
    region check runs before the model is ever called, so that move is never
    on the table."""
    client = StubRouterClient(
        tool_input=_attainment_input(segment="Enterprise", restated="guessed")
    )
    answer = ask("how is the West region doing this quarter", data, client)

    assert client.calls == []
    assert isinstance(answer, Refused)
    assert str(data.region_mismatch_count) in answer.reason


def test_slack_sentiment_refuses_with_the_catalog_coverage_list(data):
    catalog = build_catalog(data)
    answer = ask("what did our Slack sentiment look like", data)

    assert isinstance(answer, Refused)
    for spec in catalog.metrics:
        assert spec.name in answer.hint


def test_question_naming_no_quarter_resolves_online_and_restates_it(data):
    client = StubRouterClient(
        tool_input=_attainment_input(
            restated=(
                "Reading this as attainment across the whole organization for "
                "Q2-2026, the quarter containing the as-of date, since the "
                "question named no quarter."
            ),
        )
    )
    answer = ask("how are we tracking", data, client)

    assert isinstance(answer, Answered)
    assert answer.router_mode == "online"
    assert "Q2-2026" in answer.restated
    assert "named no quarter" in answer.restated


def test_unknown_segment_from_the_model_refuses_rather_than_answering(data):
    client = StubRouterClient(
        tool_input=_attainment_input(
            segment="Nonexistent Segment", restated="a made-up segment"
        )
    )
    answer = ask("how is the Fictional segment doing", data, client)

    assert isinstance(answer, Refused)
    assert "not in the catalog" in answer.reason


def test_model_api_unreachable_falls_back_offline_with_a_populated_restatement(data):
    client = StubRouterClient(raises=ConnectionError("model API unreachable"))
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.router_mode == "offline"
    assert answer.restated
    assert "Q2-2026" in answer.restated


def test_offline_router_refuses_a_question_matching_no_metric_rather_than_guess(data):
    answer = ask("what's the weather forecast for next week", data)

    assert isinstance(answer, Refused)
    assert answer.router_mode == "offline"
    assert answer.intent is not None
    assert answer.intent.restated
