"""Turning a question into a structured intent.

Issue 01 shipped the offline keyword router. Issue 03 puts the Anthropic
tool-use router in front of it: tool choice forced to a single tool whose
input schema is `Intent`'s own JSON schema, enums populated from the catalog.
The keyword router stays as the fallback for when that call fails, since a
network outage should degrade a live demo, not crash it.

The router prompt is built entirely from the catalog - metric names,
descriptions, examples, segments, reps, managers, periods, the as-of date. It
never receives a data row, so it is structurally incapable of leaking a
number into the prompt; the no-hallucinated-numbers guarantee rests on what
the model was never shown, not on prompt wording.

Region questions are refused before either router runs. `Intent` has no field
for region, so the one wrong move available to a model asked about it is
substituting the nearest segment or rep - a substitution validation can't
catch, since the substituted value would be a real one. Catching it here,
ahead of both routers, means it can't happen regardless of which one answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .catalog import Catalog
from .config import ROUTER_MODEL
from .domain import UNSUPPORTED, Intent
from .periods import period_of

STOPWORDS = {
    "a", "about", "against", "am", "and", "any", "are", "as", "at", "be", "by",
    "did", "do", "does", "doing", "for", "from", "get", "give", "going", "have",
    "how", "i", "in", "is", "it", "its", "just", "many", "me", "much", "of",
    "on", "our", "right", "show", "so", "that", "the", "their", "them", "there",
    "to", "us", "was", "we", "were", "what", "whats", "when", "where", "which",
    "who", "why", "with", "you", "your",
}

# Period words never decide which metric was asked for. Without this, a bare
# "what happened last quarter" would score against every metric that mentions a
# quarter in its examples.
PERIOD_WORDS = {
    "q1", "q2", "quarter", "quarterly", "this", "current", "last", "previous",
    "now", "today", "period", "2026", "first", "second",
}

# Explicit quarter names never trigger the "named no quarter" caveat in the
# restatement. "this quarter" and "last quarter" do, because they are relative
# to `as_of` rather than a name the question actually used.
EXPLICIT_PERIOD_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bq1\b|\bfirst quarter\b", "Q1-2026"),
    (r"\bq2\b|\bsecond quarter\b", "Q2-2026"),
)
CURRENT_PERIOD_PATTERN = r"\bthis quarter\b|\bcurrent quarter\b|\bright now\b"
LAST_PERIOD_PATTERN = r"\blast quarter\b|\bprevious quarter\b"

GROUPING_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(by|per|each|across) segments?\b", "segment"),
    (r"\b(by|per|each|across) reps?\b|\bby sales ?rep\b", "rep"),
    (r"\b(by|per|each|across) managers?\b", "manager"),
)

Mode = Literal["online", "offline"]


@dataclass(frozen=True)
class Routing:
    intent: Intent
    mode: Mode


def _words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in STOPWORDS and t not in PERIOD_WORDS}


def _metric_vocabulary(catalog: Catalog) -> dict[str, set[str]]:
    """What each registered metric answers to, read off its own declaration."""
    vocabulary: dict[str, set[str]] = {}
    for spec in catalog.metrics:
        text = " ".join((spec.name, spec.description, *spec.examples))
        vocabulary[spec.name] = _words(text) | {spec.name}
    return vocabulary


def _match_metric(question: str, catalog: Catalog) -> tuple[str | None, str | None]:
    asked = _words(question)
    scores = {
        name: len(asked & vocab) for name, vocab in _metric_vocabulary(catalog).items()
    }
    if not scores or max(scores.values()) == 0:
        return None, "no registered metric matches the words in this question"

    best = max(scores.values())
    winners = [name for name, score in scores.items() if score == best]
    if len(winners) > 1:
        return None, (
            "this question matches "
            + " and ".join(winners)
            + " equally well, so it is ambiguous"
        )
    return winners[0], None


def _current_period(catalog: Catalog) -> str:
    """The period `as_of` falls in - the ADR-0005 default for a bare question."""
    return period_of(catalog.as_of) or catalog.periods[-1]


def _match_period(question: str, catalog: Catalog) -> tuple[str, bool]:
    """The period, and whether the restatement owes the reader a caveat.

    An explicit "Q1"/"Q2" needs no caveat. "this quarter" resolves off
    `as_of` and is said out loud even though it happens to land on the same
    period a bare question would default to. No quarter named at all is the
    ADR-0005 default, which also gets the caveat.
    """
    lowered = question.lower()
    for pattern, period in EXPLICIT_PERIOD_PATTERNS:
        if re.search(pattern, lowered) and period in catalog.periods:
            return period, False

    current = _current_period(catalog)
    if re.search(CURRENT_PERIOD_PATTERN, lowered):
        return current, True
    if re.search(LAST_PERIOD_PATTERN, lowered):
        index = catalog.periods.index(current)
        return catalog.periods[max(index - 1, 0)], True

    return current, True


def _match_value(question: str, values: tuple[str, ...]) -> str | None:
    lowered = question.lower()
    for value in values:
        if re.search(rf"\b{re.escape(value.lower())}\b", lowered):
            return value
    return None


def _match_rep(question: str, catalog: Catalog) -> str | None:
    named = _match_value(question, catalog.reps)
    if named:
        return named
    first_names = [name.split()[0] for name in catalog.reps]
    lowered = question.lower()
    for full, first in zip(catalog.reps, first_names):
        if first_names.count(first) == 1 and re.search(
            rf"\b{re.escape(first.lower())}\b", lowered
        ):
            return full
    return None


def _match_grouping(
    question: str, segment: str | None, rep: str | None, manager: str | None
) -> str:
    lowered = question.lower()
    for pattern, grouping in GROUPING_PATTERNS:
        if re.search(pattern, lowered):
            return grouping
    if rep:
        return "rep"
    if manager:
        return "manager"
    if segment:
        return "segment"
    return "overall"


def restate(
    *,
    metric: str,
    grouping: str,
    period: str,
    period_defaulted: bool,
    segment: str | None = None,
    rep: str | None = None,
    manager: str | None = None,
) -> str:
    """The one sentence that renders inside the answer, templated from the intent."""
    if rep:
        scope = f"for {rep}"
    elif manager:
        scope = f"for the team under {manager}"
    elif segment:
        scope = f"for the {segment} segment"
    elif grouping == "overall":
        scope = "across the whole organization"
    else:
        scope = f"broken out by {grouping}"

    sentence = f"Reading this as {metric} {scope} for {period}"
    if period_defaulted:
        sentence += (
            ", the quarter containing the as-of date, "
            "since the question named no quarter"
        )
    return sentence + "."


REGION_WORD_PATTERN = r"\bregions?\b"


def _mentions_region(question: str, catalog: Catalog) -> bool:
    lowered = question.lower()
    if re.search(REGION_WORD_PATTERN, lowered):
        return True
    return any(
        re.search(rf"\b{re.escape(region.lower())}\b", lowered)
        for region in catalog.regions
    )


def _region_intent(question: str, catalog: Catalog) -> Intent:
    """Refuse a region question before either router runs.

    Reuses `_match_period` so a region refusal still names an assumed quarter
    the same way any other restatement would, rather than skipping the ADR-0005
    caveat just because the question is being refused.
    """
    period, defaulted = _match_period(question, catalog)
    sentence = f"Reading this as a question about region for {period}"
    if defaulted:
        sentence += (
            ", the quarter containing the as-of date, "
            "since the question named no quarter"
        )
    sentence += ", which this system refuses to answer."
    return Intent(
        metric=UNSUPPORTED,
        grouping="overall",
        period=period,
        restated=sentence,
        unsupported_reason=catalog.region_refusal_reason(),
    )


def route_offline(question: str, catalog: Catalog) -> Intent:
    """Keyword routing. Refuses rather than guesses when nothing matches."""
    period, defaulted = _match_period(question, catalog)
    metric, why_not = _match_metric(question, catalog)

    if metric is None:
        return Intent(
            metric=UNSUPPORTED,
            grouping="overall",
            period=period,
            restated=(
                "Reading this as a question I could not match to a metric, "
                f"for {period}."
            ),
            unsupported_reason=why_not,
        )

    segment = _match_value(question, catalog.segments)
    manager = _match_value(question, catalog.managers)
    rep = _match_rep(question, catalog)
    grouping = _match_grouping(question, segment, rep, manager)

    return Intent(
        metric=metric,
        grouping=grouping,
        period=period,
        segment=segment,
        rep=rep,
        manager=manager,
        restated=restate(
            metric=metric,
            grouping=grouping,
            period=period,
            period_defaulted=defaulted,
            segment=segment,
            rep=rep,
            manager=manager,
        ),
    )


TOOL_NAME = "route_question"


def _tool_schema(catalog: Catalog) -> dict:
    """`Intent`'s own JSON schema, with enums populated from the catalog.

    Forcing tool choice to this schema is what makes the model structurally
    unable to answer with free-form JSON in a text reply, and populating the
    enums from the catalog is what makes it structurally unable to name a
    metric, segment, rep, manager, or period the system doesn't have.
    """
    schema = Intent.model_json_schema()
    props = schema["properties"]
    props["metric"]["enum"] = [*catalog.metric_names(), UNSUPPORTED]
    props["grouping"]["enum"] = list(catalog.groupings)
    props["period"]["enum"] = list(catalog.periods)
    for field, values in (
        ("comparison_period", catalog.periods),
        ("segment", catalog.segments),
        ("rep", catalog.reps),
        ("manager", catalog.managers),
    ):
        props[field]["anyOf"][0]["enum"] = list(values)
    return schema


def _system_prompt(catalog: Catalog) -> str:
    """Everything the model gets: catalog metadata, never a data row.

    Column names and the distinct values of low-cardinality columns (segment,
    rep, manager, period) are here. No deal, no dollar figure, no account
    name - the router is structurally incapable of leaking a number into the
    prompt because none was ever put in it.
    """
    metrics = "\n".join(
        f"- {spec.name} (answers at: {', '.join(spec.groupings)}): {spec.description}\n"
        + "\n".join(f'    e.g. "{example}"' for example in spec.examples)
        for spec in catalog.metrics
    )
    return (
        "You route a sales leader's question about pipeline into a structured "
        "intent by calling the route_question tool. You never see any deal-level "
        "data - only this catalog of what the system can answer.\n\n"
        f"Metrics:\n{metrics}\n\n"
        f"Segments: {', '.join(catalog.segments)}\n"
        f"Reps: {', '.join(catalog.reps)}\n"
        f"Managers: {', '.join(catalog.managers)}\n"
        f"Periods: {', '.join(catalog.periods)}\n"
        f"As-of date: {catalog.as_of}\n\n"
        "Rules:\n"
        f"- If the question names no quarter, default period to "
        f"{_current_period(catalog)}, the quarter containing the as-of date, and "
        "say so explicitly in `restated` - a wrong default has to be as visible "
        "as a wrong metric.\n"
        "- If the question needs a metric, segment, or rep outside the lists "
        "above, or asks about something this catalog doesn't cover, set metric "
        "to 'unsupported' and explain why in `unsupported_reason`. Never "
        "substitute the closest match - refusing is cheap, a wrong route is "
        "expensive.\n"
        "- `restated` is one sentence restating how you read the question. It "
        "renders directly to the user, so a wrong reading has to be visible in "
        "it alone.\n"
    )


def route_online(question: str, catalog: Catalog, client: object) -> Routing:
    """The Anthropic tool-use router: tool choice forced to the one tool."""
    message = client.messages.create(
        model=ROUTER_MODEL,
        max_tokens=1024,
        system=_system_prompt(catalog),
        tools=[
            {
                "name": TOOL_NAME,
                "description": (
                    "Record the structured reading of the sales leader's question."
                ),
                "input_schema": _tool_schema(catalog),
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": question}],
    )
    block = next(b for b in message.content if getattr(b, "type", None) == "tool_use")
    return Routing(intent=Intent(**block.input), mode="online")


def route(question: str, catalog: Catalog, client: object | None = None) -> Routing:
    """Route online with the model, falling back to the offline keyword router.

    Region is checked before either router runs and short-circuits both,
    since `Intent` has no field to hold a region and the one wrong move
    available to a model asked about it is silently substituting the nearest
    segment or rep - a substitution validation has no way to catch, because
    the substituted value would be a real one.
    """
    if _mentions_region(question, catalog):
        mode: Mode = "online" if client is not None else "offline"
        return Routing(intent=_region_intent(question, catalog), mode=mode)

    if client is not None:
        try:
            return route_online(question, catalog, client)
        except Exception:
            pass

    return Routing(intent=route_offline(question, catalog), mode="offline")
