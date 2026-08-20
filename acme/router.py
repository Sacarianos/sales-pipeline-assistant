"""Turning a question into a structured intent.

Issue 01 ships the offline keyword router only - no language model is called
anywhere in this file. Issue 03 adds the Anthropic tool-use path in front of it
and keeps this one as the fallback for when that call fails.

The keyword router misroutes more often than a model would, and a misroute is
the one failure the verifier cannot catch, so it refuses when matching is
ambiguous rather than guessing, and it always populates `restated` so a human
can spot a wrong reading from the answer alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .catalog import Catalog
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

    current = period_of(catalog.as_of) or catalog.periods[-1]
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


def route(question: str, catalog: Catalog, client: object | None = None) -> Routing:
    """Route a question, offline for now.

    The signature takes a client because issue 03 adds the Anthropic tool-use
    router in front of the keyword path and falls back to this one on failure.
    """
    return Routing(intent=route_offline(question, catalog), mode="offline")
