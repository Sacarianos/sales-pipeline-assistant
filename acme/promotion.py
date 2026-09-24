"""Turning a recurring exploratory plan into a registered metric. See the V3
spec.

`find_candidates` reads the query log and groups answered plans that mean
the same thing once the snapshot, the period, and any segment, rep, or
manager scope are set aside, since the metric supplies those per question.
`problems` lists what a person still has to decide before a candidate can
become a metric, and `promote` writes the metric file only when that list
is empty. The person writes the definition. The tool refuses to write it for
them.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .definitions import DEFINITIONS
from .domain import Intent
from .loading import Data
from .periods import PERIODS
from .promoted import PERIOD_FRAMES, SCOPE_COLUMNS, PromotedPlanFailed, compute_plan, concrete_plan
from .query_log import LogRecord
from .query_plan import PlanRejection, QueryPlan, run
from .registry import MetricRequest, get as registered_metric

# The snapshot frames collapse to one, since the metric picks the snapshot
# from the period each question asks about.
SNAPSHOT_FRAMES = {"deals_q1": "deals", "deals_q2": "deals"}
SCOPE_FIELDS = {column: field for field, column in SCOPE_COLUMNS.items()}
GROUPINGS = tuple(SCOPE_COLUMNS)
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MIN_DEFINITION_WORDS = 8


@dataclass(frozen=True)
class Candidate:
    id: str
    # The plan with its frame generalized to `deals`, `quotas`, or `reps`,
    # and no period or scope filters. What the metric file will hold.
    plan: dict
    count: int
    questions: tuple[str, ...]
    # Scope values logged plans filtered on, by grouping, which suggests the
    # groupings the metric should answer at.
    scope_seen: dict[str, tuple[str, ...]]
    # The plan as the metric would run it for the current period.
    description: str


@dataclass(frozen=True)
class Promotion:
    """What a person decided about a candidate."""

    name: str
    description: str
    groupings: tuple[str, ...]
    examples: tuple[str, ...]
    definition_keys: tuple[str, ...]


class PromotionRefused(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _normalize(raw: dict) -> tuple[dict, dict[str, str]] | None:
    try:
        plan = QueryPlan(**raw)
    except ValidationError:
        return None
    filters, scope = [], {}
    for spec in plan.filters:
        if spec.column == "period":
            continue
        field = SCOPE_FIELDS.get(spec.column)
        if field and spec.op == "eq" and isinstance(spec.value, str):
            scope[field] = spec.value
            continue
        filters.append(spec)
    general = plan.model_copy(
        update={
            "frame": SNAPSHOT_FRAMES.get(plan.frame, plan.frame),
            "filters": filters,
            "decline_reason": None,
        }
    )
    return general.model_dump(exclude_defaults=True), scope


def _intent(period: str, **scope: str) -> Intent:
    return Intent(metric="promoted", grouping=next(iter(scope), "overall"), period=period, restated="", **scope)


def _describe(template: dict, data: Data) -> str | None:
    """How the metric reads the plan for the current period, or None when
    the plan no longer passes the checker."""
    from .fallback import frames, schemas

    plan, _ = concrete_plan(template, _intent(PERIODS[-1]))
    outcome = run(plan, frames(data), schemas(data))
    return None if isinstance(outcome, PlanRejection) else outcome.description


def find_candidates(records: list[LogRecord], data: Data) -> list[Candidate]:
    """Answered plans grouped by what they mean, most asked first."""
    groups: dict[str, dict] = {}
    for record in records:
        if record.outcome != "answered" or record.plan is None:
            continue
        normalized = _normalize(record.plan)
        if normalized is None:
            continue
        template, scope = normalized
        key = json.dumps(template, sort_keys=True)
        group = groups.setdefault(key, {"template": template, "count": 0, "questions": [], "scope": {}})
        group["count"] += 1
        if record.question not in group["questions"]:
            group["questions"].append(record.question)
        for field, value in scope.items():
            seen = group["scope"].setdefault(field, [])
            if value not in seen:
                seen.append(value)

    candidates = []
    for key, group in groups.items():
        description = _describe(group["template"], data)
        if description is None:
            continue
        candidates.append(
            Candidate(
                id=hashlib.sha1(key.encode()).hexdigest()[:8],
                plan=group["template"],
                count=group["count"],
                questions=tuple(group["questions"]),
                scope_seen={field: tuple(values) for field, values in group["scope"].items()},
                description=description,
            )
        )
    return sorted(candidates, key=lambda c: -c.count)


def _sample_scopes(data: Data, groupings: tuple[str, ...]) -> list[dict[str, str]]:
    """Overall plus one real value per grouping, for the trial run."""
    reps = data.reps
    samples = {"segment": reps["segment"].iloc[0], "rep": reps["rep_name"].iloc[0], "manager": reps["manager"].iloc[0]}
    return [{}] + [{grouping: samples[grouping]} for grouping in groupings]


def problems(promotion: Promotion, candidate: Candidate, data: Data) -> list[str]:
    """Everything still missing or wrong. Empty means the metric can be written."""
    found = []
    if not NAME_PATTERN.match(promotion.name):
        found.append(f"name '{promotion.name}' must be snake_case, like loss_reasons")
    elif registered_metric(promotion.name) is not None:
        found.append(f"a metric named '{promotion.name}' is already registered")

    description = " ".join(promotion.description.split())
    if not description:
        found.append("write a definition: what this metric means, in a sentence or two")
    elif description == candidate.description:
        found.append("the definition is the machine's description of the plan. Write it in your own words")
    elif len(description.split()) < MIN_DEFINITION_WORDS:
        found.append(f"the definition needs at least {MIN_DEFINITION_WORDS} words to say what the metric means")

    for grouping in promotion.groupings:
        if grouping not in GROUPINGS:
            found.append(f"'{grouping}' is not a grouping. Choose from {', '.join(GROUPINGS)}")
    if not promotion.examples:
        found.append("give at least one example question")
    for key in promotion.definition_keys:
        if key not in DEFINITIONS:
            found.append(f"'{key}' is not a definition. Choose from {', '.join(sorted(DEFINITIONS))}")

    if found:
        return found

    for period in PERIODS:
        for scope in _sample_scopes(data, promotion.groupings):
            request = MetricRequest(intent=_intent(period, **scope), data=data, as_of=data.as_of)
            try:
                compute_plan(request, candidate.plan, definition_keys=promotion.definition_keys)
            except PromotedPlanFailed as exc:
                where = ", ".join(f"{k} {v}" for k, v in scope.items()) or "overall"
                found.append(f"the metric fails for {period}, {where}: {exc}")
    return found


# --- rendering --------------------------------------------------------------


def _literal(value: object, indent: int = 0) -> str:
    """A Python literal for plain JSON-shaped data, in the repo's style."""
    pad = " " * indent
    inner = " " * (indent + 4)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{json.dumps(k)}: {_literal(v, indent + 4)}," for k, v in value.items()]
        return "{\n" + "\n".join(items) + f"\n{pad}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]" if isinstance(value, list) else "()"
        items = [f"{inner}{_literal(v, indent + 4)}," for v in value]
        open_, close = ("[", "]") if isinstance(value, list) else ("(", ")")
        return open_ + "\n" + "\n".join(items) + f"\n{pad}{close}"
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def _wrapped_string(text: str, indent: int) -> str:
    lines = textwrap.wrap(" ".join(text.split()), width=72 - indent)
    chunks = [json.dumps(line + (" " if i < len(lines) - 1 else ""), ensure_ascii=False) for i, line in enumerate(lines)]
    pad = " " * indent
    return "(\n" + "\n".join(f"{pad}    {chunk}" for chunk in chunks) + f"\n{pad})"


def render(promotion: Promotion, candidate: Candidate) -> str:
    groupings = ("overall", *promotion.groupings)
    intent_fields = ("period", "grouping", *promotion.groupings)
    period_note = (
        "It reads the rows of the period each question asks about, from the "
        "snapshot that owns that period."
        if candidate.plan["frame"] in PERIOD_FRAMES
        else "The reps frame has no period, so every question reads the whole roster."
    )
    docstring = textwrap.fill(
        "`PLAN` is what the exploratory lane ran before a person promoted it "
        "and wrote the definition in `description`. It is data, not code. "
        "`acme.promoted` builds the concrete plan for each question and "
        "runs it through the same checker and pandas as the exploratory lane. "
        + period_note,
        width=76,
    )
    promoted_from = {"count": candidate.count, "questions": candidate.questions}
    return f'''"""{promotion.name}: promoted from an exploratory query plan.

{docstring}
"""

from __future__ import annotations

from ..domain import Result
from ..promoted import compute_plan
from ..registry import MetricRequest, metric

PLAN = {_literal(candidate.plan)}

# What the query log held when this was promoted.
PROMOTED_FROM = {_literal(promoted_from)}

DEFINITION_KEYS = {_literal(tuple(promotion.definition_keys))}


@metric(
    name={json.dumps(promotion.name)},
    description={_wrapped_string(promotion.description, 4)},
    groupings={_literal(groupings, 4)},
    intent_fields={_literal(intent_fields, 4)},
    definition_keys=DEFINITION_KEYS,
    examples={_literal(tuple(promotion.examples), 4)},
)
def {promotion.name}(request: MetricRequest) -> Result:
    return compute_plan(request, PLAN, definition_keys=DEFINITION_KEYS)
'''


def promote(promotion: Promotion, candidate: Candidate, data: Data, metrics_dir: Path) -> Path:
    """Write the metric file, or raise `PromotionRefused` and write nothing."""
    found = problems(promotion, candidate, data)
    path = Path(metrics_dir) / f"{promotion.name}.py"
    if path.exists():
        found.append(f"{path} already exists")
    if found:
        raise PromotionRefused(found)
    source = render(promotion, candidate)
    compile(source, str(path), "exec")
    path.write_text(source, encoding="utf-8")
    return path


__all__ = ["Candidate", "Promotion", "PromotionRefused", "find_candidates", "problems", "promote", "render"]
