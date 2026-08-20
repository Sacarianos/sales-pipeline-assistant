"""Flags: one rule function per assumption, all of them run, all of them shown.

Each rule takes the intent, the result, and the loaded data, and returns a
`Flag` or `None`. All rules run and all results are collected, because the
list itself is what the UI renders in the panel without a click, rather than
being buried as conditionals inside metric code.

Issue 01 shipped partial period and the plain-English metric definitions.
Issue 05 adds stale close date and missing field, the two rules that catch a
data-quality problem the sales leader wasn't asking about but needs to know
regardless. Unknown stage — the loud half of the open-as-complement decision
— rides along here too, since it needs nothing this issue didn't already add.

Issue 06 adds snapshot divergence and changed deals, both reading the change
log the loader now diffs at load time. Issue 07 adds the invented-rule
disclosure for risk, so nobody repeats the 100 percent threshold as a
Acme standard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .definitions import definition, title
from .domain import Flag, Intent, Result
from .loading import CLOSED_LOST, CLOSED_STAGES, Data
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
def stale_close_date(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Open deals in the answering snapshot whose forecast close date has
    already passed as of the as-of date — pipeline that was supposed to have
    closed by now and hasn't, named so a leader doesn't forecast on it
    unknowingly. Checked against the whole snapshot that answered the
    question, not this question's filtered rows, so the caveat holds
    regardless of which segment, rep, or manager was asked about — the same
    reason `unknown_stage` reads off `data` rather than the result.
    """
    deals = data.deals(result.snapshot)
    stale = deals[~deals["stage"].isin(CLOSED_STAGES) & (deals["close_date"] <= data.as_of)]
    if stale.empty:
        return None
    names = ", ".join(f"{row.deal_id} ({row.account_name})" for row in stale.itertuples())
    return Flag(
        kind="stale_close_date",
        title="Stale close date",
        detail=(
            f"{len(stale)} open deal{'s' if len(stale) != 1 else ''} in the "
            f"{result.snapshot} snapshot carry a forecast close date at or "
            f"before {data.as_of} and have not closed: {names}."
        ),
    )


@rule
def missing_field(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Nulls in a field the answer depends on, checked against the whole
    answering snapshot for the same reason `stale_close_date` is. The only
    gap of this kind in the dataset today is a missing loss reason on a
    closed-lost deal, so this checks that field rather than scanning every
    column for nulls that carry no meaning for the metric being answered."""
    deals = data.deals(result.snapshot)
    lost = deals[deals["stage"] == CLOSED_LOST]
    missing = lost[lost["loss_reason"].isna()]
    if missing.empty:
        return None
    names = ", ".join(f"{row.deal_id} ({row.account_name})" for row in missing.itertuples())
    verb = "has" if len(missing) == 1 else "have"
    return Flag(
        kind="missing_field",
        title="Missing loss reason",
        detail=(
            f"{len(missing)} closed-lost deal{'s' if len(missing) != 1 else ''} "
            f"in the {result.snapshot} snapshot {verb} no loss reason "
            f"recorded: {names}."
        ),
    )


@rule
def snapshot_divergence(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Q1 as-reported versus restated, decomposed into what actually
    changed. Only fires at the overall grouping: the decomposition counts
    and values describe the whole Q1 portfolio, and would misdescribe a
    segment- or rep-scoped answer that only restates its own slice.
    """
    if "restated_closed_won" not in result.facts or intent.grouping != "overall":
        return None
    as_reported = result.facts["closed_won"].value
    restated = result.facts["restated_closed_won"].value
    gap = as_reported - restated
    if abs(gap) < 1:
        return None

    div = data.divergence
    return Flag(
        kind="snapshot_divergence",
        title="Q1 as-reported versus restated",
        detail=(
            f"As-reported Q1 closed-won is {as_reported:,.0f}; restated from the "
            f"Q2 snapshot it is {restated:,.0f}, a gap of {gap:,.0f}. Of that gap, "
            f"{div.unwon_count} deal{'s' if div.unwon_count != 1 else ''} worth "
            f"{div.unwon_value:,.0f} genuinely came unwon, and "
            f"{div.reused_unwon_count} deal ID{'s' if div.reused_unwon_count != 1 else ''} "
            f"worth {div.reused_unwon_value:,.0f} were reused by a different account and "
            "were never unwon at all. The remainder is deals whose close date moved "
            "across the quarter boundary between snapshots."
        ),
    )


@rule
def changed_deals(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Deals in this answer's own source rows that differ between the two
    snapshots, so a leader who remembers a different figure for a deal they
    know understands why before assuming the tool is wrong."""
    if result.source_rows.empty or data.change_log.empty:
        return None
    present = set(result.source_rows["deal_id"]) & set(data.change_log["deal_id"])
    if not present:
        return None
    by_deal = data.change_log[data.change_log["deal_id"].isin(present)].drop_duplicates("deal_id")
    names = ", ".join(
        f"{row.deal_id} ({row.change_type})" for row in by_deal.sort_values("deal_id").itertuples()
    )
    return Flag(
        kind="changed_deals",
        title="Deals changed between snapshots",
        detail=(
            f"{len(present)} deal{'s' if len(present) != 1 else ''} in this answer's "
            f"source rows changed between the Q1 and Q2 snapshots: {names}."
        ),
    )


@rule
def invented_risk_rule(intent: Intent, result: Result, data: Data) -> Flag | None:
    """Discloses that the 100 percent best-case threshold is this system's
    own invention, not a Acme standard — and that pace was explicitly
    rejected as the underlying rule, since at day 32 of a young quarter
    pace would flag nearly everyone."""
    if intent.metric != "risk":
        return None
    return Flag(
        kind="invented_rule",
        title="Invented threshold",
        detail=(
            "Below 100 percent best-case coverage is a threshold this system "
            "invented for this analysis, not a Acme standard. A pace-based "
            "rule was rejected on purpose: early in a quarter, most reps have "
            "closed nothing yet, and pace would flag nearly everyone without "
            "telling a leader anything they could act on."
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
