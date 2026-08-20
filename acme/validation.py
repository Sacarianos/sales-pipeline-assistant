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


@dataclass(frozen=True)
class ValidationError:
    reason: str


def _rep_row(data: Data, rep_name: str):
    matches = data.reps[data.reps["rep_name"] == rep_name]
    return matches.iloc[0] if len(matches) else None


def check_filter_agreement(intent: Intent, data: Data) -> ValidationError | None:
    """One rule over any pair among rep, segment, and manager.

    Manager is a strict function of segment in this data, so a manager paired
    with the wrong segment is exactly as nonsensical as a rep paired with the
    wrong segment. Silently dropping one of two conflicting filters would
    answer a different question than the one asked, so this refuses instead.
    """
    if not intent.rep:
        if intent.segment and intent.manager:
            seg_managers = set(
                data.reps.loc[data.reps["segment"] == intent.segment, "manager"]
            )
            if intent.manager not in seg_managers:
                return ValidationError(
                    f"manager '{intent.manager}' does not manage the "
                    f"'{intent.segment}' segment"
                )
        return None

    rep_row = _rep_row(data, intent.rep)
    if rep_row is None:
        return ValidationError(f"rep '{intent.rep}' is not in the catalog")

    if intent.segment and rep_row["segment"] != intent.segment:
        return ValidationError(
            f"rep '{intent.rep}' belongs to the '{rep_row['segment']}' segment, "
            f"not '{intent.segment}'"
        )
    if intent.manager and rep_row["manager"] != intent.manager:
        return ValidationError(
            f"rep '{intent.rep}' reports to '{rep_row['manager']}', "
            f"not '{intent.manager}'"
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
