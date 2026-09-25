"""The chat's conversation behavior, run through the real app with
Streamlit's test harness and a scripted model client."""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from acme import config

APP = Path(__file__).resolve().parent.parent / "app.py"
FIRST = "how is the Enterprise segment doing"
FOLLOW_UP = "what about SMB?"
PROSE = "Here is how that segment is tracking."


class _Block:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class ScriptedClient:
    """Reads the first question as Enterprise attainment and every later one
    as a follow-up about SMB. Kept on the class so a test can inspect the
    one instance the app creates."""

    instances: list["ScriptedClient"] = []

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        self.messages = self
        ScriptedClient.instances.append(self)

    def router_calls(self) -> list[dict]:
        return [call for call in self.calls if call.get("tools")]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs.get("tools"):
            return _Block(content=[_Block(type="text", text=PROSE)])
        follow_up = len(self.router_calls()) > 1
        reading = dict(
            metric="attainment",
            grouping="segment",
            segment="SMB" if follow_up else "Enterprise",
            period="Q2-2026",
            follows_up=follow_up,
            restated=(
                "Following on from your last question, reading this as attainment for the SMB segment for Q2-2026."
                if follow_up
                else "Reading this as attainment for the Enterprise segment for Q2-2026."
            ),
        )
        return _Block(content=[_Block(type="tool_use", input=reading)])


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(anthropic, "Anthropic", ScriptedClient)
    monkeypatch.setattr(config, "QUERY_LOG_PATH", tmp_path / "query_log.jsonl")
    ScriptedClient.instances.clear()
    st.cache_resource.clear()
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    yield at
    st.cache_resource.clear()


def _ask(at: AppTest, question: str) -> None:
    at.chat_input[0].set_value(question).run()


def _new_conversation(at: AppTest):
    return next(button for button in at.sidebar.button if button.label == "New conversation")


def test_a_follow_up_shows_what_it_carried_over_before_the_answer(app):
    _ask(app, FIRST)
    _ask(app, FOLLOW_UP)

    answer = list(app.chat_message[-1].children.values())
    assert type(answer[0]).__name__ == "Caption"
    assert answer[0].value.startswith("↳ Following on from your last question")
    prose_at = next(i for i, node in enumerate(answer) if getattr(node, "value", None) == PROSE)
    assert prose_at > 0


def test_a_standalone_answer_shows_no_carried_over_caption(app):
    _ask(app, FIRST)

    first = list(app.chat_message[-1].children.values())[0]
    assert not str(getattr(first, "value", "")).startswith("↳")


def test_the_second_question_reaches_the_router_with_the_first_as_context(app):
    _ask(app, FIRST)
    _ask(app, FOLLOW_UP)

    [client] = ScriptedClient.instances
    first_call, second_call = client.router_calls()
    assert json.dumps(first_call["messages"]) == json.dumps([{"role": "user", "content": FIRST}])
    context = second_call["messages"][0]["content"]
    assert FIRST in context and context.endswith(f"Question: {FOLLOW_UP}")


def test_new_conversation_is_available_after_the_first_answer_and_clears_it(app):
    """The button used to be drawn before the question was answered, so it
    stayed disabled after the first answer until something else reran."""
    assert _new_conversation(app).disabled

    _ask(app, FIRST)
    assert len(app.chat_message) == 2
    assert not _new_conversation(app).disabled

    _new_conversation(app).click().run()
    assert len(app.chat_message) == 0
    assert _new_conversation(app).disabled
