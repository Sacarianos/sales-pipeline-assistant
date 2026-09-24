"""What the assistant remembers from earlier in a conversation. See
docs/specs/conversation-memory.md.

A `Turn` keeps a question and how it was read: the intent for a metric
answer, the query plan for an exploratory one. It never keeps the prose, the
facts, the table, or any figure the answer produced. The router and the
generator have never been shown a data figure, and a remembered answer would
hand them one to carry into a filter or a restatement, where nothing checks
it against the data. A follow-up changes what was asked, not what was
answered, so the reading is all it needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Literal

from .domain import Answer

MEMORY_TURNS = 3

Lane = Literal["metric", "exploratory", "refused"]


@dataclass(frozen=True)
class Turn:
    question: str
    lane: Lane
    restated: str
    # The router's reading, without its restatement, for metric answers and
    # for refusals that had one.
    intent: dict | None
    # The plan that ran, for exploratory answers.
    plan: dict | None


def turn(question: str, answer: Answer) -> Turn:
    reading = None
    if answer.intent is not None:
        reading = answer.intent.model_dump(exclude_none=True, exclude={"restated", "unsupported_reason"})
    if answer.kind == "refused":
        restated = answer.intent.restated if answer.intent is not None else ""
        return Turn(question=question, lane="refused", restated=restated, intent=reading, plan=None)
    return Turn(
        question=question,
        lane=answer.lane,
        restated=answer.restated,
        intent=reading,
        plan=answer.plan,
    )


def remember(turns: Iterable[Turn]) -> tuple[Turn, ...]:
    """The turns a new question is read against: the most recent few."""
    return tuple(turns)[-MEMORY_TURNS:]


def last_plan(history: Iterable[Turn]) -> dict | None:
    """The most recent exploratory plan, which a refinement changes."""
    plans = [t.plan for t in history if t.lane == "exploratory" and t.plan is not None]
    return plans[-1] if plans else None


def _line(index: int, remembered: Turn) -> str:
    if remembered.lane == "refused":
        return f'{index}. "{remembered.question}" was refused.'
    if remembered.lane == "exploratory":
        return (
            f'{index}. "{remembered.question}" was answered by an exploratory query. '
            f"{remembered.restated} Plan: {json.dumps(remembered.plan)}"
        )
    return (
        f'{index}. "{remembered.question}" was answered by a metric, read as '
        f"{json.dumps(remembered.intent)}"
    )


def prompt_for(question: str, history: Iterable[Turn]) -> str:
    """The user message a model gets: earlier readings, then the question.
    With no history it's the question alone, exactly as before memory."""
    turns = remember(history)
    if not turns:
        return question
    lines = "\n".join(_line(i, t) for i, t in enumerate(turns, start=1))
    return (
        "Earlier in this conversation, oldest first. Each line is a question "
        "and how it was read, never what it answered:\n"
        f"{lines}\n\n"
        f"Question: {question}"
    )


__all__ = ["MEMORY_TURNS", "Turn", "last_plan", "prompt_for", "remember", "turn"]
