"""Query time: route, validate, compute, flag, render. One early exit.

This is the primary seam. It takes a question string, the loaded data, and an
injected model client, and returns an `Answer` — `Answered` or `Refused`. No
orchestration framework sits underneath it; it is a straight line with one
early exit for a refusal.
"""

from __future__ import annotations

from .catalog import Catalog, build_catalog
from .domain import Answer, Answered, Refused
from .flags import evaluate as evaluate_flags
from .loading import Data
from .registry import MetricRequest
from .router import route
from .validation import validate


def ask(question: str, data: Data, client: object | None = None) -> Answer:
    catalog = build_catalog(data)
    routing = route(question, catalog, client)
    intent = routing.intent

    error = validate(intent, catalog, data)
    if error is not None:
        return Refused(
            reason=error.reason,
            hint=catalog.coverage_hint(),
            intent=intent,
            router_mode=routing.mode,
        )

    spec = catalog.metric(intent.metric)
    assert spec is not None  # validate() already confirmed this
    request = MetricRequest(intent=intent, data=data, as_of=data.as_of)
    result = spec.compute(request)

    flags = evaluate_flags(intent, result, data)

    # Issue 04 replaces this with the narrator's prose plus verification.
    # The template sentence is the deterministic fallback every result
    # carries, so the spine has something correct to show before the model
    # is in the loop at all.
    return Answered(
        prose=result.template,
        prose_source="template",
        verified_figures=None,
        facts=result.facts,
        flags=flags,
        table=result.table,
        source_rows=result.source_rows,
        filters=result.filters,
        snapshot=result.snapshot,
        intent=intent,
        router_mode=routing.mode,
    )
