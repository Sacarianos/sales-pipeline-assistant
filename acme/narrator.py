"""Writing prose from facts alone, and blocking it before it reaches the
screen if any figure in it doesn't check out.

The narrator receives the question, the restatement, and the facts. Nothing
else — not the aggregate table, not the source rows, not the flags. Giving it
anything more would give the model a place to draw a number the verifier
never checks.

`narrate` is the one entry point, mirroring how `router.route` hides its own
online/offline split behind a single call. Two triggers land on the same
template fallback: an outright API failure or timeout, and a verification
failure. There is always something correct to publish, so the worst case is
a boring answer, never an error or an empty screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import NARRATOR_MODEL
from .domain import Fact
from .verifier import verify

Source = Literal["narrator", "template"]


@dataclass(frozen=True)
class Narration:
    prose: str
    source: Source
    verified_figures: int | None
    blocked: bool
    # The model's prose when verification blocked it, and the figures in it
    # that matched no fact. Kept for diagnosis, never published.
    draft: str = ""
    unmatched: tuple[str, ...] = ()


SYSTEM_PROMPT = (
    "You write a short, direct answer for a sales leader from the figures "
    "you are given below. Rules:\n"
    "- Use only the figures supplied. Never introduce a number that isn't "
    "listed, and never compute a new one by adding, subtracting, or "
    "otherwise combining the figures you were given.\n"
    "- Write every figure in full, exactly as given. No shorthand ('4.05M', "
    "'1.99K'), no rounding to a different precision than what's shown.\n"
    "- Two or three sentences. Lead with the answer in the first sentence.\n"
    "- Do not hedge, and do not suggest checking a dashboard or another "
    "report — you are the report."
)


def _facts_block(facts: dict[str, Fact]) -> str:
    return "\n".join(f"- {fact.label}: {fact.formatted()}" for fact in facts.values())


def _user_prompt(question: str, restated: str, facts: dict[str, Fact]) -> str:
    return (
        f"Question: {question}\n"
        f"Restated: {restated}\n\n"
        f"Figures:\n{_facts_block(facts)}\n\n"
        "Write the answer."
    )


def _call_model(
    question: str, restated: str, facts: dict[str, Fact], client: object
) -> str | None:
    """Returns the narrator's prose, or `None` on any API failure or timeout."""
    try:
        message = client.messages.create(
            model=NARRATOR_MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(question, restated, facts)}],
        )
        block = next(b for b in message.content if getattr(b, "type", None) == "text")
        return block.text
    except Exception:
        return None


def narrate(
    question: str,
    restated: str,
    facts: dict[str, Fact],
    template: str,
    client: object | None,
) -> Narration:
    """Write and verify prose from `facts` alone, falling back to `template`
    when there's no client, the call fails, or verification blocks it."""
    if client is None:
        return Narration(prose=template, source="template", verified_figures=None, blocked=False)

    prose = _call_model(question, restated, facts, client)
    if prose is None:
        return Narration(prose=template, source="template", verified_figures=None, blocked=True)

    result = verify(prose, facts, context=restated)
    if not result.ok:
        return Narration(
            prose=template, source="template", verified_figures=None, blocked=True,
            draft=prose, unmatched=result.unmatched,
        )

    return Narration(
        prose=prose, source="narrator", verified_figures=result.verified_count, blocked=False
    )
