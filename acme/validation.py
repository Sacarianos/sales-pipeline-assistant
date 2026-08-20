"""The checks the model can't express, run after the router produces an intent.

The model validates its own tool call against the JSON schema; this module
covers what schema validation cannot: that the period actually exists, that
rep/segment/manager filters agree with each other, and that the metric is
implemented at the grouping the question asked for. Every failure returns a
refusal carrying a reason and a catalog hint, never a nearest-match guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .domain import UNSUPPORTED, Intent
from .loading import Data
from .periods import is_in_progress


@dataclass(frozen=True)
class ValidationError:
    reason: str


def _rep_row(data: Data, rep_name: str):
    matches = data.reps[data.reps["rep_name"] == rep_name]
    return matches.iloc[0] if len(matches) else None


def _implied_segment_and_manager(
    data: Data, kind: str, value: str
) -> tuple[str | None, str | None]:
    """What (segment, manager) pair a single filter value implies.

    Resolved through the rep-to-segment and rep-to-manager lookup in the quota
    source (`data.reps`), which is what lets one rule cover all three filters
    instead of three near-duplicate checks. A side left `None` means that
    filter alone doesn't pin it down — a segment implies no manager if it maps
    to more than one, which never happens in this data but costs nothing to
    handle. Callers must already know `value` is in the catalog: `validate`
    checks rep/segment/manager membership before this ever runs.
    """
    if kind == "rep":
        row = _rep_row(data, value)
        assert row is not None
        return row["segment"], row["manager"]
    if kind == "segment":
        managers = set(data.reps.loc[data.reps["segment"] == value, "manager"])
        return value, managers.pop() if len(managers) == 1 else None
    segments = set(data.reps.loc[data.reps["manager"] == value, "segment"])
    return (segments.pop() if len(segments) == 1 else None), value


def check_filter_agreement(intent: Intent, data: Data) -> ValidationError | None:
    """One rule over any pair among rep, segment, and manager.

    Manager is a strict function of segment in this data, so a manager paired
    with the wrong segment is exactly as nonsensical as a rep paired with the
    wrong segment. Silently dropping one of two conflicting filters would
    answer a different question than the one asked, so this refuses instead.
    """
    named = [
        (kind, value)
        for kind, value in (("rep", intent.rep), ("segment", intent.segment), ("manager", intent.manager))
        if value
    ]
    resolved = [
        (kind, value, _implied_segment_and_manager(data, kind, value))
        for kind, value in named
    ]

    for i, (kind_a, value_a, (seg_a, mgr_a)) in enumerate(resolved):
        for kind_b, value_b, (seg_b, mgr_b) in resolved[i + 1 :]:
            if seg_a is not None and seg_b is not None and seg_a != seg_b:
                return ValidationError(
                    f"{kind_a} '{value_a}' and {kind_b} '{value_b}' disagree: "
                    f"{kind_a} '{value_a}' implies the '{seg_a}' segment, "
                    f"{kind_b} '{value_b}' implies the '{seg_b}' segment"
                )
            if mgr_a is not None and mgr_b is not None and mgr_a != mgr_b:
                return ValidationError(
                    f"{kind_a} '{value_a}' and {kind_b} '{value_b}' disagree: "
                    f"{kind_a} '{value_a}' implies manager '{mgr_a}', "
                    f"{kind_b} '{value_b}' implies manager '{mgr_b}'"
                )
    return None


def validate(intent: Intent, catalog: Catalog, data: Data) -> ValidationError | None:
    """Return the first validation failure, or None if the intent may proceed."""
    if intent.is_unsupported():
        return ValidationError(intent.unsupported_reason or "question is out of scope")

    if intent.period not in catalog.periods:
        return ValidationError(f"period '{intent.period}' is not in the catalog")

    spec = catalog.metric(intent.metric)
    if spec is None:
        return ValidationError(f"metric '{intent.metric}' is not registered")
    if not spec.supports(intent.grouping):
        return ValidationError(
            f"'{intent.metric}' does not answer at the '{intent.grouping}' grouping"
        )

    if intent.metric == "risk" and not is_in_progress(intent.period, data.as_of):
        return ValidationError(
            f"risk is a best-case read on a quarter still in progress; "
            f"{intent.period} is not in progress as of {data.as_of}, so there is "
            "nothing left that could still close"
        )

    if intent.segment and intent.segment not in catalog.segments:
        return ValidationError(f"segment '{intent.segment}' is not in the catalog")
    if intent.manager and intent.manager not in catalog.managers:
        return ValidationError(f"manager '{intent.manager}' is not in the catalog")
    if intent.rep and intent.rep not in catalog.reps:
        return ValidationError(f"rep '{intent.rep}' is not in the catalog")

    agreement = check_filter_agreement(intent, data)
    if agreement is not None:
        return agreement

    return None
