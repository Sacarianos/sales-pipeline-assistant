"""The exploratory fallback lane: a question the registry doesn't cover
reaches a generator, comes back as a pandas expression, runs through
`acme.sandbox`, and returns an answer instead of a refusal.

`attempt` is the one entry point, mirroring how `router.route` and
`narrator.narrate` each hide their own online/offline or verify/fallback
split behind a single call. It returns `None` whenever the lane can't answer
— no client, no model, a decline, or a rejected expression — and `None` is
the pipeline's signal to fall through to the ordinary catalog refusal. This
lane never refuses on its own; it only ever answers or steps aside.

The generator sees column names, dtypes, and the distinct values of
low-cardinality columns, the same shape the router prompt already uses. It
never receives a data row: identifier columns and date columns are excluded
from the schema description because their cardinality is close to the row
count, not because of a rule specific to them.

Facts are derived generically from whatever shape the sandboxed expression
returns, capped at a small number of rows. A result too large to summarize
as named facts gets none, which is deliberate: the verifier can then never
let the narrator cite a row value nobody vetted, and the deterministic
template — which only ever states the row count, not row contents — carries
the answer instead.
"""

from __future__ import annotations

import ast

import pandas as pd
from pydantic import BaseModel, Field

from .config import ROUTER_MODEL
from .domain import Answered, Fact, Unit
from .loading import Data
from .narrator import narrate
from .sandbox import ROW_CAP, SandboxRejection, SandboxResult, run as sandbox_run

FRAME_NAMES = ("deals_q1", "deals_q2", "quotas", "reps")

# Enforced by the sandbox itself, not by the prompt: an expression may name
# deals_q1 or deals_q2, never both. This is what makes "there is no combined
# frame and no way to ask for one" true regardless of how an expression
# tries to combine them — concatenation, a join, or plain arithmetic between
# two aggregates — rather than resting on the generator following the
# system prompt's instruction not to.
SNAPSHOT_FRAMES = frozenset({"deals_q1", "deals_q2"})

# A result this small can be summarized as individually-labelled Facts a
# narrator could cite. Above it, no per-row facts are produced at all, so
# the verifier has nothing to let a citation of an unvetted row pass
# against, and the template's row count is what publishes instead.
FACT_ROW_CAP = 8

LOW_CARDINALITY_THRESHOLD = 15

TOOL_NAME = "generate_pandas_expression"


class FallbackPlan(BaseModel):
    """What the generator returns: an expression to run, or a decline.

    Exactly one of the two is meant to carry content; `attempt` treats a
    non-empty `decline_reason` as a decline regardless of `expression`,
    since declining is the safer read of an ambiguous response.
    """

    expression: str | None = Field(
        default=None,
        description="A single pandas expression over the frames below that answers the question.",
    )
    decline_reason: str | None = Field(
        default=None,
        description=(
            "Why this question can't be answered from the frames below, if it can't — "
            "for example, a column the question needs doesn't exist. Leave empty if "
            "`expression` is set."
        ),
    )


def _frames(data: Data) -> dict[str, pd.DataFrame]:
    """The frames the lane may name, bound to the same objects the metrics
    use. Named per snapshot — there is no combined frame and no way to ask
    for one, since silently blending the two snapshots would reintroduce the
    exact error the reconciler exists to prevent."""
    return {
        "deals_q1": data.deals("Q1"),
        "deals_q2": data.deals("Q2"),
        "quotas": data.quotas,
        "reps": data.reps,
    }


def _describe_column(frame: pd.DataFrame, column: str) -> str:
    dtype = str(frame[column].dtype)
    if dtype in ("object", "str") or dtype.startswith("string"):
        values = sorted({str(v) for v in frame[column].dropna().unique()})
        if len(values) <= LOW_CARDINALITY_THRESHOLD:
            return f"    - {column} ({dtype}): {values}"
    return f"    - {column} ({dtype})"


def _describe_frame(name: str, frame: pd.DataFrame) -> str:
    lines = [f"  {name} ({len(frame)} rows):"]
    lines.extend(_describe_column(frame, column) for column in frame.columns)
    return "\n".join(lines)


def _schema_prompt(data: Data) -> str:
    frames = _frames(data)
    return "\n".join(_describe_frame(name, frame) for name, frame in frames.items())


def _system_prompt(data: Data) -> str:
    """Everything the generator gets: frame schemas, never a data row.

    Identifier columns (deal_id, account_name) and date columns are absent
    from the low-cardinality listing not because of a rule naming them, but
    because their distinct-value count is close to the row count — the same
    mechanism that keeps the router's prompt free of a data row applies here
    unchanged.
    """
    return (
        "You write a single pandas expression that answers a sales leader's "
        f"question, called through the {TOOL_NAME} tool. You never see any "
        "deal-level data, only the frame schemas below.\n\n"
        f"Frames available (reference no others):\n{_schema_prompt(data)}\n\n"
        "Rules:\n"
        "- Reference only deals_q1, deals_q2, quotas, and reps. There is no "
        "combined frame and no way to build one - never write an expression "
        "that reads both deals_q1 and deals_q2, whether by concatenating "
        "them, merging them, or combining an aggregate from each with an "
        "arithmetic operator or method (+, .add, .sub, and similar). If the "
        "question doesn't name a quarter, answer from deals_q2 alone, the "
        "current snapshot, rather than combining both.\n"
        "- Reference only the frames above - no pandas module functions "
        "(pd.concat, pd.merge) and no builtins. Only method calls on one of "
        "the four frames are available.\n"
        "- Prefer the 'period' column ('Q1-2026' / 'Q2-2026') over comparing "
        "close_date directly; there is no safe way to construct a date "
        "literal in this sandbox.\n"
        "- Set `expression` to exactly one pandas expression, or set "
        "`decline_reason` and leave `expression` empty if the question needs "
        "a column that doesn't exist above. Decline rather than substitute "
        "the nearest-looking column.\n"
        "- Only method calls on a frame are permitted - no imports, no "
        "lambdas, no comprehensions, no bare function calls.\n"
    )


def _generate(question: str, data: Data, client: object) -> FallbackPlan | None:
    """Returns the generator's plan, or `None` on any API failure."""
    try:
        message = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=1024,
            system=_system_prompt(data),
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Record the pandas expression that answers the question, or a decline.",
                    "input_schema": FallbackPlan.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": question}],
        )
        block = next(b for b in message.content if getattr(b, "type", None) == "tool_use")
        return FallbackPlan(**block.input)
    except Exception:
        return None


def _referenced_frames(expression: str) -> tuple[str, ...]:
    """Which of the allowlisted frames the expression actually names, for
    the filters panel. Best-effort: a syntax error yields an empty tuple
    rather than raising, since `sandbox.run` is what's responsible for
    turning a bad expression into a rejection."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return ()
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return tuple(name for name in FRAME_NAMES if name in names)


def _is_numeric_scalar(value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) or (
        hasattr(value, "item") and getattr(value, "dtype", None) is not None
    )


def _facts_from_result(value: object) -> dict[str, Fact]:
    """Facts derived generically from whatever shape the sandboxed
    expression returned.

    A row count is always a fact when the result is tabular, regardless of
    size, so the narrator always has at least one true thing it can safely
    say. Individual row values join it only up to `FACT_ROW_CAP`: past that,
    no per-row facts are produced at all, so the verifier has nothing to
    validate an unvetted row citation against, and a result too large to
    summarize can still be narrated by its count without ever letting the
    narrator speak to contents nobody vetted.
    """
    if isinstance(value, pd.Series):
        value = value.rename(value.name or "value").reset_index()

    if isinstance(value, pd.DataFrame):
        facts: dict[str, Fact] = {
            "row_count": Fact(float(len(value)), Unit.COUNT, "Rows returned by the query")
        }
        if len(value) > FACT_ROW_CAP:
            return facts
        for i, row in enumerate(value.itertuples(index=False)):
            row_dict = row._asdict()
            label_bits = [str(v) for v in row_dict.values() if not _is_numeric_scalar(v)]
            label = " / ".join(label_bits) if label_bits else f"row {i + 1}"
            for column, cell in row_dict.items():
                if _is_numeric_scalar(cell):
                    facts[f"row{i}_{column}"] = Fact(float(cell), Unit.NUMBER, f"{label}: {column}")
        return facts

    if _is_numeric_scalar(value):
        return {"result": Fact(float(value), Unit.NUMBER, "Result")}

    return {}


def _template(expression: str, value: object, row_count: int | None, truncated: bool) -> str:
    if isinstance(value, pd.DataFrame):
        count = row_count if row_count is not None else len(value)
        note = f", showing the first {ROW_CAP}" if truncated else ""
        return (
            f"This exploratory query returned {count} row{'s' if count != 1 else ''}"
            f"{note}. Expression: {expression}"
        )
    return f"This exploratory query's result is {value}. Expression: {expression}"


def attempt(
    question: str, data: Data, client: object | None
) -> Answered | None:
    """Try to answer `question` from the fallback lane.

    Returns `None` whenever the lane can't answer for any reason at all -
    no client, an unreachable API, a decline, or a rejected expression - so
    the caller always has one thing to check before falling through to the
    catalog refusal.
    """
    if client is None:
        return None

    plan = _generate(question, data, client)
    if plan is None:
        return None
    if plan.decline_reason or not plan.expression:
        return None

    outcome = sandbox_run(
        plan.expression, _frames(data), mutually_exclusive=(SNAPSHOT_FRAMES,)
    )
    if isinstance(outcome, SandboxRejection):
        return None

    assert isinstance(outcome, SandboxResult)
    facts = _facts_from_result(outcome.value)
    template = _template(plan.expression, outcome.value, outcome.row_count, outcome.truncated)

    if isinstance(outcome.value, pd.Series):
        display = outcome.value.rename(outcome.value.name or "value").reset_index()
    elif isinstance(outcome.value, pd.DataFrame):
        display = outcome.value
    else:
        display = pd.DataFrame([{"result": outcome.value}])

    frames_read = _referenced_frames(plan.expression)
    filters = {
        "frames read": ", ".join(frames_read) if frames_read else "none referenced",
        "row cap": f"first {ROW_CAP} of {outcome.row_count}" if outcome.truncated else "no truncation",
    }

    # Same contract as a metric's answer: the narrator sees only the
    # question, a restatement, and the facts just derived, and its prose is
    # verified against those facts before publishing.
    restated = f"Reading this as an exploratory query: {plan.expression}"
    narration = narrate(question, restated, facts, template, client)

    return Answered(
        lane="exploratory",
        expression=plan.expression,
        restated=restated,
        prose=narration.prose,
        prose_source=narration.source,
        verified_figures=narration.verified_figures,
        narrator_blocked=narration.blocked,
        facts=facts,
        table=display,
        source_rows=display,
        filters=filters,
        snapshot="",
        intent=None,
        router_mode="online",
    )


__all__ = ["FallbackPlan", "attempt"]
