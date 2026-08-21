"""Quarter boundaries and period membership.

A deal belongs to the quarter its `close_date` falls in, whether the deal is
open or closed. No other date field determines period.
"""

from __future__ import annotations

from datetime import date, timedelta

QUARTERS: dict[str, tuple[date, date]] = {
    "Q1-2026": (date(2026, 1, 1), date(2026, 3, 31)),
    "Q2-2026": (date(2026, 4, 1), date(2026, 6, 30)),
}

PERIODS = tuple(QUARTERS)


def bounds(period: str) -> tuple[date, date]:
    return QUARTERS[period]


def period_of(when: date | None) -> str | None:
    """The period a close date falls in, or None if it falls outside both."""
    if when is None:
        return None
    for period, (start, end) in QUARTERS.items():
        if start <= when <= end:
            return period
    return None


def days_in_quarter(period: str) -> int:
    start, end = bounds(period)
    return (end - start).days + 1


def day_of_quarter(period: str, as_of: date) -> int:
    """Which day of the quarter `as_of` is, clamped to the quarter's own range.

    A past quarter reads as complete; a future one reads as day zero.
    """
    start, end = bounds(period)
    if as_of < start:
        return 0
    if as_of > end:
        return days_in_quarter(period)
    return (as_of - start).days + 1


def is_in_progress(period: str, as_of: date) -> bool:
    start, end = bounds(period)
    return start <= as_of <= end


def date_for_day_of_quarter(period: str, day: int) -> date:
    """The calendar date that is day `day` of `period`, clamped to the
    quarter's own range.

    Matching by day of quarter rather than calendar date is what lets day 32
    of Q2 (May 2) compare fairly against day 32 of Q1 (February 1) instead of
    against the calendar date May 2 in a quarter that hasn't reached it yet.
    """
    start, end = bounds(period)
    candidate = start + timedelta(days=max(day, 1) - 1)
    return min(candidate, end)


def year_of(period: str) -> int:
    return bounds(period)[0].year


def snapshot_for(period: str) -> str:
    """The snapshot that answers a question about `period`.

    Q1 questions read the Q1 snapshot as reported. Q2 questions read Q2.
    """
    return "Q1" if period == "Q1-2026" else "Q2"


def period_for_snapshot(snapshot: str) -> str:
    """The inverse of `snapshot_for`: the period a snapshot name stands for.

    Needed by callers that land on a snapshot first - the fallback lane
    knows which deals frame a generated expression named before it knows
    anything about a period - and then need the period key flag rules like
    `partial_period` are written against.
    """
    return "Q1-2026" if snapshot == "Q1" else "Q2-2026"
