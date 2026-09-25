"""Issue 02: the exploratory fallback lane, and the region refusal that
short-circuits ahead of it.

Per the parent spec's testing decisions, most of this goes in through the
primary seam - `ask(question, data, client)` - and asserts on what reaches
the screen. `frames` and the generator's schema prompt are checked directly
in a few places, the same way the parent spec treats the query plan checker
as a deliberate second seam. The frame boundary, the hidden region columns,
and the no-data-row guarantee are what this lane exists to hold, so they're
pinned directly and not only inferred.
"""

from __future__ import annotations

import re

import pytest

from acme import fallback
from acme.domain import Answered, Refused
from acme.pipeline import ask
from tests.test_llm_router_and_refusals import StubRouterClient


class _ToolUseBlock:
    def __init__(self, input: dict):
        self.type = "tool_use"
        self.input = input


class _TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, content):
        self.content = content


class FallbackStubClient:
    """Dispatches by which tool (if any) a call requested, so one stub can
    stand in for the router's call, the generator's call, and the
    narrator's plain-text call within a single `ask()` invocation, each
    returning a different, test-controlled response."""

    def __init__(
        self,
        *,
        router_input: dict,
        plan_input: dict | None = None,
        narrator_text: str | None = None,
    ):
        self.router_input = router_input
        self.plan_input = plan_input
        self.narrator_text = narrator_text
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        tools = kwargs.get("tools")
        if not tools:
            if self.narrator_text is None:
                raise RuntimeError("no narrator text configured for this stub")
            return _Message([_TextBlock(self.narrator_text)])
        tool_name = tools[0]["name"]
        if tool_name == "route_question":
            return _Message([_ToolUseBlock(self.router_input)])
        if tool_name == fallback.TOOL_NAME:
            if self.plan_input is None:
                raise RuntimeError("no plan configured for this stub")
            return _Message([_ToolUseBlock(self.plan_input)])
        raise AssertionError(f"unexpected tool requested: {tool_name}")

    def generator_call(self) -> dict:
        return next(c for c in self.calls if c.get("tools", [{}])[0].get("name") == fallback.TOOL_NAME)


def _unsupported_input(reason: str = "no registered metric covers this") -> dict:
    return dict(
        metric="unsupported",
        grouping="overall",
        period="Q2-2026",
        restated="Reading this as a question outside the catalog for Q2-2026.",
        unsupported_reason=reason,
    )


def test_a_loss_reason_question_answers_in_the_fallback_lane_with_a_table(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}],
            "group_by": ["loss_reason"],
            "aggregate": {"function": "count"},
            "sort_by": "result",
        },
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "exploratory"
    assert not answer.table.empty


def test_a_metric_question_answers_in_the_metric_lane_not_the_fallback(data):
    client = StubRouterClient(
        tool_input=dict(
            metric="attainment",
            grouping="overall",
            period="Q2-2026",
            restated="Reading this as attainment across the whole organization for Q2-2026.",
        )
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "metric"
    # The router's call and the narrator's both happen, but the fallback
    # lane is never reached, so no call ever requests the generator's tool.
    requested_tools = [c["tools"][0]["name"] for c in client.calls if c.get("tools")]
    assert fallback.TOOL_NAME not in requested_tools


def test_the_generator_prompt_contains_no_data_row(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    ask("why are we losing deals", data, client)

    system_prompt = client.generator_call()["system"]
    for account in data.deals("Q2")["account_name"].unique():
        assert account not in system_prompt
    for deal_id in data.deals("Q2")["deal_id"].unique():
        assert deal_id not in system_prompt


def test_a_plan_naming_both_snapshots_refuses_rather_than_answering(data):
    """A plan names one frame, so there is no plan that reads both
    snapshots. A frame value that tries to name both is just a frame nobody
    has, rejected before anything runs."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q1 + deals_q2",
            "aggregate": {"function": "sum", "column": "deal_value"},
        },
    )
    answer = ask("what's our combined pipeline across both quarters", data, client)

    assert isinstance(answer, Refused)
    assert "not one of the frames" in answer.reason


def test_a_rejected_plan_refuses_with_its_reason_and_the_catalog_hint(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "filters": [{"column": "stage", "op": "eq", "value": "Closed-Lost"}],
            "aggregate": {"function": "count"},
        },
    )
    answer = ask("how many deals did we lose", data, client)

    assert isinstance(answer, Refused)
    assert "'Closed-Lost' is not a value of 'stage'" in answer.reason
    from acme.catalog import build_catalog

    assert answer.hint == build_catalog(data).coverage_hint()


def test_a_decline_tells_the_reader_why(data):
    """User story 7: a question needing a column nobody has says so, rather
    than falling back to the generic coverage refusal alone."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"decline_reason": "no column in these frames covers Slack sentiment"},
    )
    answer = ask("what did our Slack sentiment look like", data, client)

    assert isinstance(answer, Refused)
    assert "No column in these frames covers Slack sentiment." in answer.reason


@pytest.mark.parametrize(
    "payload",
    [
        "deals_q2.agg('to_csv', path_or_buf='{path}')",
        "9 ** 9 ** 9",
    ],
)
def test_generated_code_is_never_run(data, tmp_path, payload):
    """Regression for the V2 sandbox: `agg` dispatched a string argument to
    any frame method, so this first payload wrote a file while the reader
    saw a refusal, and the last one hung the process. A plan has no field
    that takes code, so a payload in the old shape is a plan with no frame."""
    target = tmp_path / "pwned.csv"
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": payload.format(path=target.as_posix())},
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Refused)
    assert not target.exists()


def test_a_plan_over_either_region_column_refuses(data):
    """Region refuses ahead of both lanes when the question says "region".
    A question that avoids the word, like "which part of the country", reaches
    the fallback, which grouped by the deal-side region column and picked a
    definition silently. The region columns are hidden from the plan now,
    so that plan is rejected before it runs, and the refusal says the
    column is withheld rather than pretending it doesn't exist."""
    for column in ("region", "rep_region"):
        client = FallbackStubClient(
            router_input=_unsupported_input(),
            plan_input={
                "frame": "deals_q2",
                "group_by": [column],
                "aggregate": {"function": "sum", "column": "deal_value"},
            },
        )
        answer = ask("which part of the country has the most pipeline", data, client)

        assert isinstance(answer, Refused)
        assert f"'{column}' is withheld" in answer.reason


def test_the_generator_is_never_shown_a_region_column(data):
    prompt = fallback._system_prompt(data)
    schema = fallback._tool_schema(data)
    column_lines = [line for line in prompt.splitlines() if line.strip().startswith("- ") and "(" in line]
    assert not any("region" in line for line in column_lines)
    assert "region" not in str(schema)


def test_territory_refuses_as_region_before_any_model_call(data):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input={"frame": "deals_q2"})
    answer = ask("which territory has the most pipeline", data, client)

    assert isinstance(answer, Refused)
    assert "Region is out of scope" in answer.reason
    assert client.calls == []


def test_a_long_result_still_gives_the_narrator_its_first_rows(data):
    """Found live: a top-20 accounts answer gave the narrator only two
    counts, and it wrote that the answer wasn't determinable, with the
    answer in the table right under it."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "group_by": ["account_name"],
            "aggregate": {"function": "sum", "column": "deal_value"},
            "sort_by": "result",
            "limit": 20,
        },
    )
    answer = ask("which accounts have the most pipeline", data, client)

    assert isinstance(answer, Answered)
    row_facts = [key for key in answer.facts if re.match(r"row\d+_", key)]
    assert len(row_facts) == fallback.FACT_ROW_CAP
    assert answer.facts["rows_described"].value == fallback.FACT_ROW_CAP
    assert "row7_sum_deal_value" in answer.facts
    assert "row8_sum_deal_value" not in answer.facts


def test_prose_citing_a_figure_absent_from_facts_is_blocked(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
        narrator_text="The total pipeline value is 999999999, a huge number.",
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "exploratory"
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True


def test_fallback_degrades_to_a_refusal_when_the_model_api_is_unreachable(data):
    client = StubRouterClient(raises=ConnectionError("model API unreachable"))
    answer = ask("why are we losing deals", data, client)
    assert isinstance(answer, Refused)
