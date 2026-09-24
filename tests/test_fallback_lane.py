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

from acme import config, fallback
from acme.domain import Answered, Refused, Unit
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


def test_an_exploratory_answer_still_carries_a_restatement(data):
    """The fallback lane has no `Intent`, but it owes the reader the same
    backstop against a silent misroute every other answer carries."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    assert answer.restated
    assert "Q2 snapshot" in answer.restated


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


def test_an_account_level_question_answers_in_the_fallback_lane(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "group_by": ["account_name"],
            "aggregate": {"function": "sum", "column": "deal_value"},
            "sort_by": "result",
            "limit": 5,
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
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
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
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
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
    frames = fallback.frames(data)
    assert set(frames) == {"deals_q1", "deals_q2", "quotas", "reps"}
    assert frames["deals_q1"] is data.deals("Q1")
    assert frames["deals_q2"] is data.deals("Q2")


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
        "deals_q2.to_csv('{path}')",
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


def test_the_generator_is_told_to_decline_a_refused_topic_rather_than_substitute(data):
    """Found live: "which territory has the most pipeline" came back as
    segment totals, since the region columns were withheld and segment was
    the nearest column left. Withholding a column isn't enough when the
    model can't tell a refused topic from a missing one."""
    prompt = fallback._system_prompt(data)
    assert "region" in prompt and "territory" in prompt
    assert "never answer it with another column" in prompt


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


def test_a_decline_reason_stands_as_its_own_sentence(data):
    """Found live: splicing the model's reason in after "and" either left a
    capital mid-sentence or, lowercased, turned "Slack" into "slack"."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"decline_reason": "Slack sentiment isn't in these frames."},
    )
    answer = ask("what did our Slack sentiment look like", data, client)

    assert isinstance(answer, Refused)
    assert answer.reason.endswith(
        "An exploratory query was tried too. Slack sentiment isn't in these frames."
    )


def test_a_rejection_reason_stands_as_its_own_sentence(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "group_by": ["region"], "aggregate": {"function": "count"}},
    )
    answer = ask("which part of the country has the most pipeline", data, client)

    assert isinstance(answer, Refused)
    assert "An exploratory query was tried too. The query written for it was rejected: " in answer.reason


def test_an_exploratory_answer_says_in_plain_english_what_it_computed(data):
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
    assert answer.query_description == (
        "Number of deals in the Q2 snapshot where stage is Closed Lost, "
        "grouped by loss reason, sorted by the result, highest first."
    )


def test_a_true_or_false_filter_reads_naturally_for_deals(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "filters": [{"column": "is_lost", "op": "eq", "value": True}],
            "aggregate": {"function": "count"},
        },
    )
    answer = ask("how many deals did we lose", data, client)

    assert isinstance(answer, Answered)
    assert answer.query_description == "Number of deals in the Q2 snapshot where the deal is lost."
    assert answer.query_description in answer.restated


def test_a_group_with_no_value_is_labelled_blank_not_by_row_number(data):
    """A closed-lost deal with no loss reason groups under a missing key. Its
    fact still needs a label a reader can place, not "row 7"."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}],
            "group_by": ["loss_reason"],
            "aggregate": {"function": "count"},
        },
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    labels = [fact.label for fact in answer.facts.values()]
    assert "blank: count" in labels
    assert not any(label.startswith("row ") for label in labels)


def test_a_listed_deal_is_labelled_by_its_first_two_text_columns(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "columns": ["deal_id", "account_name", "stage", "deal_value"],
            "sort_by": "deal_value",
            "limit": 1,
        },
    )
    answer = ask("what's our biggest deal", data, client)

    assert isinstance(answer, Answered)
    top = data.deals("Q2").sort_values("deal_value", ascending=False).iloc[0]
    assert answer.facts["row0_deal_value"].label == f"{top['deal_id']} / {top['account_name']}: deal_value"


def test_a_total_of_deal_value_is_a_currency_fact(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.facts["result"].unit is Unit.CURRENCY
    assert answer.facts["matched_rows"].value == len(data.deals("Q2"))


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


def test_prose_citing_only_verified_figures_publishes(data):
    total = float(data.deals("Q2")["deal_value"].sum())
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
        narrator_text=f"The total pipeline value across all deals is {total:,.0f}.",
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "narrator"
    assert answer.verified_figures == 1


def test_the_generator_uses_the_router_model_configuration_constant(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
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
