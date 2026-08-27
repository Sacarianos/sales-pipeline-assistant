"""Issue 02: the exploratory fallback lane, and the region refusal that
short-circuits ahead of it.

Per the parent spec's testing decisions, most of this goes in through the
primary seam - `ask(question, data, client)` - and asserts on what reaches
the screen. `_frames` and the generator's schema prompt are checked directly
in a couple of places, the same way the parent spec treats the sandbox
validator as a deliberate second seam: the frame boundary and the
no-data-row guarantee are exactly the properties this lane exists to hold,
so they're worth pinning against directly rather than only inferring them.
"""

from __future__ import annotations

from acme import config, fallback
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
        if tool_name == "generate_pandas_expression":
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


def test_an_exploratory_answer_still_carries_a_restatement(data):
    """The fallback lane has no `Intent`, but it owes the reader the same
    backstop against a silent misroute every other answer carries."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2['deal_value'].sum()"},
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    assert answer.restated
    assert "deals_q2" in answer.restated


def test_a_loss_reason_question_answers_in_the_fallback_lane_with_a_table(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "expression": (
                "deals_q2[deals_q2['stage'] == 'Closed Lost']['loss_reason'].value_counts()"
            )
        },
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "exploratory"
    assert not answer.table.empty


def test_an_account_level_question_answers_in_the_fallback_lane(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "expression": (
                "deals_q2.groupby('account_name')['deal_value'].sum().nlargest(5)"
            )
        },
    )
    answer = ask("which accounts have the most pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "exploratory"
    assert len(answer.table) == 5


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


def test_region_refuses_and_no_generation_is_attempted(data):
    client = FallbackStubClient(router_input=_unsupported_input(), plan_input={"expression": "1"})
    answer = ask("how is the West region doing this quarter", data, client)

    assert isinstance(answer, Refused)
    assert client.calls == []


def test_product_line_is_answered_by_the_metric_lane_not_refused(data):
    """Product line was briefly a refused topic here, short-circuiting ahead
    of the fallback lane on the same footing as region. It isn't one.

    Region refuses because two definitions of it measurably disagree, on 17
    of 92 deals. Product line has no second definition to disagree with, so
    the refusal was resting on an assumption about bundled deals rather than
    on anything in the data. It has its own metric now, with that assumption
    disclosed as a flag, and this pins both halves of that: it answers, and
    it answers from the registry rather than falling through to generated
    code, since a question a metric covers must never reach the fallback.
    """
    answer = ask("how is our pipeline broken out by product line", data)

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "product_mix"
    assert answer.lane == "metric"
    assert any(flag.kind == "product_line_attribution" for flag in answer.flags)


def test_a_question_needing_a_column_nobody_has_refuses_rather_than_answering(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"decline_reason": "no column in these frames covers Slack sentiment"},
    )
    answer = ask("what did our Slack sentiment look like", data, client)

    assert isinstance(answer, Refused)
    assert answer.hint


def test_the_generator_prompt_contains_no_data_row(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2['deal_value'].sum()"},
    )
    ask("why are we losing deals", data, client)

    system_prompt = client.generator_call()["system"]
    for account in data.deals("Q2")["account_name"].unique():
        assert account not in system_prompt
    for deal_id in data.deals("Q2")["deal_id"].unique():
        assert deal_id not in system_prompt


def test_low_cardinality_columns_are_listed_but_identifiers_and_dates_are_not(data):
    prompt = fallback._system_prompt(data)
    assert "Core Platform" in prompt
    assert "Closed Won" in prompt
    for account in data.deals("Q2")["account_name"].unique():
        assert account not in prompt
    for deal_id in data.deals("Q2")["deal_id"].unique():
        assert deal_id not in prompt


def test_the_lane_exposes_per_snapshot_frames_and_no_combined_frame(data):
    frames = fallback._frames(data)
    assert set(frames) == {"deals_q1", "deals_q2", "quotas", "reps"}
    assert frames["deals_q1"] is data.deals("Q1")
    assert frames["deals_q2"] is data.deals("Q2")


def test_an_expression_combining_both_snapshots_refuses_rather_than_answering(data):
    """The sandbox enforces this, not the generator's compliance with a
    prompt instruction: even a plan that tries to blend deals_q1 and
    deals_q2 (arithmetic between two aggregates, here) is rejected before
    it ever runs."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "expression": (
                "deals_q1['deal_value'].sum() + deals_q2['deal_value'].sum()"
            )
        },
    )
    answer = ask("what's our combined pipeline across both quarters", data, client)

    assert isinstance(answer, Refused)


def test_a_generated_expression_failing_validation_refuses_with_the_catalog_hint(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2.to_csv('pwned.csv')"},
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Refused)
    from acme.catalog import build_catalog

    assert answer.hint == build_catalog(data).coverage_hint()


def test_prose_citing_a_figure_absent_from_facts_is_blocked(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2['deal_value'].sum()"},
        narrator_text="The total pipeline value is 999999999, a huge number.",
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.lane == "exploratory"
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True


def test_prose_citing_only_verified_figures_publishes(data):
    total = float(data.deals("Q2")["deal_value"].sum())
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2['deal_value'].sum()"},
        narrator_text=f"The total pipeline value across all deals is {total:,.0f}.",
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "narrator"
    assert answer.verified_figures == 1


def test_the_generator_uses_the_router_model_configuration_constant(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q2['deal_value'].sum()"},
    )
    ask("why are we losing deals", data, client)

    assert client.generator_call()["model"] == config.ROUTER_MODEL


def test_fallback_degrades_to_a_refusal_with_no_client_at_all(data):
    answer = ask("why are we losing deals", data)
    assert isinstance(answer, Refused)


def test_fallback_degrades_to_a_refusal_when_the_model_api_is_unreachable(data):
    client = StubRouterClient(raises=ConnectionError("model API unreachable"))
    answer = ask("why are we losing deals", data, client)
    assert isinstance(answer, Refused)
