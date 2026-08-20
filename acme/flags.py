"""Flags: one rule function per assumption, all of them run, all of them shown.

Each rule takes the intent, the result, and the loaded data, and returns a
`Flag` or `None`. The list itself is what the UI renders, so a caveat lives
here once instead of as a conditional buried inside a metric.

Issue 01 ships the two rules the spine's acceptance criteria name: partial
period and the plain-English metric definitions. The remaining rules named in
the parent spec (snapshot divergence, stale close date, small sample, missing
values, unknown stage, invented-rule disclosure) arrive with the tickets that
first produce the condition they detect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .definitions import definition, title
from .domain import Flag, Intent, Result
from .loading import Data
from .periods import day_of_quarter, days_in_quarter, is_in_progress

Rule = Callable[[Intent, Result, Data], Flag | None]

_RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    _RULES.append(fn)
    return fn


@rule
def partial_period(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Day N of the quarter, so a low attainment percentage reads as pace and
    not catastrophe."""
    period = intent.period
    if not is_in_progress(period, data.as_of):
        return None
    day = day_of_quarter(period, data.as_of)
    total = days_in_quarter(period)
    return Flag(
        kind="partial_period",
        title="Partial period",
        detail=(
            f"{period} is in progress: day {day} of {total} as of {data.as_of}. "
            "A quarter that is a third done reads low against a full quota by "
            "design, not because pace has failed."
        ),
    )


SMALL_SAMPLE_THRESHOLD = 5


@rule
def small_sample(intent: Intent, result: Result, data: Data) -> Flag | None:
    """A headline number resting on very few deals, first seen at rep grouping.

    Grouping down to a single rep is the first thing in the system that can
    produce a headline number behind only a handful of rows, so the count
    checked here is the same row count the source-rows panel shows.
    """
    count = len(result.source_rows)
    if count >= SMALL_SAMPLE_THRESHOLD:
        return None
    return Flag(
        kind="small_sample",
        title="Small sample",
        detail=(
            f"This answer rests on {count} deal{'s' if count != 1 else ''}, fewer "
            f"than the {SMALL_SAMPLE_THRESHOLD} the system treats as enough to "
            "read as more than one data point."
        ),
    )


@rule
def unknown_stage(intent: Intent, result: Result, data: Data) -> Flag | None:
    if not data.unknown_stages:
        return None
    stages = ", ".join(data.unknown_stages)
    return Flag(
        kind="unknown_stage",
        title="Unrecognized deal stage",
        detail=(
            f"The snapshot contains a stage the loader has not been told about: "
            f"{stages}. It is counted as open by exclusion rather than dropped."
        ),
    )


def _definition_flags(result: Result) -> list[Flag]:
    return [
        Flag(kind=f"definition:{key}", title=title(key), detail=definition(key))
        for key in result.definition_keys
    ]


def evaluate(intent: Intent, result: Result, data: Data) -> tuple[Flag, ...]:
    """Run every rule, then append one definition flag per key the metric named."""
    flags = [flag for fn in _RULES for flag in (fn(intent, result, data),) if flag]
    flags.extend(_definition_flags(result))
    return tuple(flags)
