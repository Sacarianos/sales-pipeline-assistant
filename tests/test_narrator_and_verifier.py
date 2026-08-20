"""Issue 04: the narrator and the verifier that blocks it.

Per the parent spec's testing decisions, these tests go in through the
primary seam - `ask(question, data, client)` - and assert on what reaches the
screen. `client` is a stub shaped like `anthropic.Anthropic`, handling both
calls the pipeline makes to it: the router's tool-use call and the
narrator's plain-text call, distinguished by whether `tools` is in the
request kwargs.
"""

from __future__ import annotations

from acme.domain import Answered
from acme.pipeline import ask


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


class _Messages:
    def __init__(self, outer: "StubClient"):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        if "tools" in kwargs:
            return _Message([_ToolUseBlock(self._outer.tool_input)])
        if self._outer.narrator_raises is not None:
            raise self._outer.narrator_raises
        return _Message([_TextBlock(self._outer.narrator_text)])


class StubClient:
    """A duck-typed stand-in for `anthropic.Anthropic` that answers both the
    router's tool-use call and the narrator's text call from one client,
    exactly as `ask` calls it."""

    def __init__(
        self,
        tool_input: dict,
        narrator_text: str | None = None,
        narrator_raises: Exception | None = None,
    ):
        self.tool_input = tool_input
        self.narrator_text = narrator_text
        self.narrator_raises = narrator_raises
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


def test_narrator_receives_only_the_question_restatement_and_facts(data):
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_text="Q2-2026 attainment is 8.4 percent: 518,000 closed-won "
        "against a 6,200,000 quota.",
    )
    ask("how are we tracking this quarter", data, client)

    narrator_call = client.calls[1]
    prompt_text = narrator_call["system"] + repr(narrator_call["messages"])

    # Nothing from the table, source rows, or flags may appear in what the
    # narrator was shown - only the question, the restatement, and the facts.
    for account in data.deals("Q2")["account_name"].unique():
        assert account not in prompt_text
    for deal_id in data.deals("Q2")["deal_id"].unique():
        assert deal_id not in prompt_text


def test_successful_verification_publishes_prose_with_a_verified_count(data):
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_text="Q2-2026 attainment is 8.4 percent: 518,000 closed-won "
        "against a 6,200,000 quota.",
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "narrator"
    assert answer.narrator_blocked is False
    assert answer.verified_figures == 4  # 2026, 8.4, 518,000, 6,200,000
    assert answer.prose == client.narrator_text


def test_prose_with_a_figure_absent_from_facts_is_discarded_for_the_template(data):
    client = StubClient(
        tool_input=_attainment_input(),
        # 999,999 appears nowhere in this answer's facts.
        narrator_text="Q2-2026 attainment is 999,999 percent of quota.",
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True
    assert answer.verified_figures is None
    assert answer.prose != client.narrator_text
    assert "999,999" not in answer.prose


def test_thousands_shorthand_of_a_currency_fact_is_blocked(data):
    # closed_won is 518,000 for the default Q2 headline; 518 is the thousands
    # shorthand of it, which the narrator is told never to write.
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_text="Q2-2026 closed-won revenue is 518 against quota.",
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True


def test_percent_count_and_date_facts_verify_only_at_rounding_precision(data):
    # day_of_quarter (32) and days_in_quarter (91) are count facts for the
    # default Q2 answer; dividing either by a thousand must not verify.
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_text="This is day 0.032 of the quarter.",
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True


def test_period_year_day_of_quarter_and_days_in_quarter_verify_as_facts(data):
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_text=(
            "It is 2026, day 32 of a 91-day quarter, with 8.4 percent "
            "attainment against a 6,200,000 quota."
        ),
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "narrator"
    assert answer.verified_figures == 5


def test_narrator_api_failure_falls_back_to_the_template(data):
    client = StubClient(
        tool_input=_attainment_input(),
        narrator_raises=ConnectionError("model API unreachable"),
    )
    answer = ask("how are we tracking this quarter", data, client)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is True
    assert answer.verified_figures is None


def test_no_client_publishes_the_template_without_a_blocked_badge(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.prose_source == "template"
    assert answer.narrator_blocked is False
    assert answer.verified_figures is None
