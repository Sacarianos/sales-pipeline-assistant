"""Query time: route, validate, compute, flag, render. One early exit, plus
V2's second lane for whatever the registry doesn't cover.

This is the primary seam. It takes a question string, the loaded data, and an
injected model client, and returns an `Answer` — `Answered` or `Refused`. No
orchestration framework sits underneath it; it is a straight line with one
early exit for a refusal.
"""

from __future__ import annotations

from typing import Sequence

from . import fallback
from .catalog import build_catalog
from .conversation import Turn
from .domain import Answer, Answered, Refused
from .flags import evaluate as evaluate_flags
from .loading import Data
from .narrator import narrate
from .query_log import QueryLog
from .registry import MetricRequest
from .router import route
from .validation import validate


def _sentence(text: str) -> str:
    """A reason as a sentence of its own. The model writes some of these and
    the lane writes others, so only the first letter is touched, and only to
    capitalize it. Lowercasing would turn "Slack" into "slack"."""
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:] + "."


def ask(
    question: str,
    data: Data,
    client: object | None = None,
    *,
    log: QueryLog | None = None,
    history: Sequence[Turn] = (),
) -> Answer:
    catalog = build_catalog(data)
    routing = route(question, catalog, client, history)
    intent = routing.intent

    # The registry is consulted first and always wins: a question a metric
    # covers must never fall through to generated code, since the metric
    # encodes a definition a human agreed to and a generated expression does
    # not. Only an intent the router itself couldn't match, and that isn't
    # a topic refused ahead of routing (region), reaches the fallback lane
    # at all.
    declined = None
    # Only a question no metric covers goes to the exploratory lane. An
    # ambiguous one, or one a metric covers at another grouping, refuses.
    if intent.is_unsupported() and not routing.refused_topic and intent.unsupported_kind in (None, "no_metric"):
        exploratory = fallback.attempt(
            question, data, client,
            router_mode=routing.mode, log=log, follows_up=intent.follows_up,
            # The router decides whether a question follows on. A standalone
            # question gets no earlier turns, so it can't inherit their scope.
            history=history if intent.follows_up else (),
        )
        if isinstance(exploratory, Answered):
            return exploratory
        declined = exploratory

    error = validate(intent, catalog, data)
    if error is not None:
        reason = error.reason
        if isinstance(declined, fallback.Declined):
            reason = f"{reason.rstrip('.')}. An exploratory query was tried too. {_sentence(declined.reason)}"
        return Refused(
            reason=reason,
            hint=catalog.coverage_hint(),
            intent=intent,
            router_mode=routing.mode,
        )

    spec = catalog.metric(intent.metric)
    assert spec is not None  # validate() already confirmed this
    request = MetricRequest(intent=intent, data=data, as_of=data.as_of)
    result = spec.compute(request)

    flags = evaluate_flags(intent, result, data)

    # The narrator sees the question, the restatement, and the facts —
    # nothing else. Its prose is verified against those same facts before
    # publishing; a blocked or failed narration falls back to the
    # deterministic template every result carries.
    narration = narrate(question, intent.restated, result.facts, result.template, client)

    return Answered(
        lane="metric",
        restated=intent.restated,
        prose=narration.prose,
        prose_source=narration.source,
        verified_figures=narration.verified_figures,
        narrator_blocked=narration.blocked,
        blocked_draft=narration.draft,
        unmatched_figures=narration.unmatched,
        facts=result.facts,
        flags=flags,
        table=result.table,
        source_rows=result.source_rows,
        filters=result.filters,
        snapshot=result.snapshot,
        intent=intent,
        router_mode=routing.mode,
    )
