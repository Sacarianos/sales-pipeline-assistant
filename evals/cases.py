"""The eval cases: questions with what a correct answer looks like.

A case is scored on outcome, not on the exact plan. Two plans can both be
right, like filtering lost deals on `stage` or on `is_lost`, so exploratory
cases compare the answer's figures to a reference computed here in pandas.
When a question doesn't say whether it means the current quarter or the
whole current snapshot, either reading passes. When it does say, like "this
quarter", only that reading passes.

Each check returns a list of failures, empty when the case passes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from acme.domain import Answer
from acme.fallback import TOOL_NAME as GENERATOR_TOOL
from acme.loading import Data

CURRENT = "Q2-2026"


@dataclass(frozen=True)
class Observed:
    answer: Answer
    # The plan the generator wrote, from the query log, when there was one.
    plan: dict | None
    tools_called: tuple[str, ...]


Check = Callable[[Observed, Data], list[str]]


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    # "metric", "exploratory", or "refused": where a correct answer lands.
    expect: str
    checks: tuple[Check, ...] = ()
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# --- checks -----------------------------------------------------------------


def routed(metric: str, grouping: str = "overall", period: str = CURRENT, **fields: str) -> Check:
    def check(observed: Observed, data: Data) -> list[str]:
        intent = observed.answer.intent
        if intent is None:
            return ["no intent to check"]
        wanted = {"metric": metric, "grouping": grouping, "period": period, **fields}
        return [
            f"{key} was {getattr(intent, key)!r}, expected {value!r}"
            for key, value in wanted.items()
            if getattr(intent, key) != value
        ]

    return check


def no_generation(observed: Observed, data: Data) -> list[str]:
    if GENERATOR_TOOL in observed.tools_called:
        return ["the exploratory generator was called for a topic refused ahead of it"]
    return []


def _deals(data: Data, whole_snapshot: bool) -> pd.DataFrame:
    deals = data.deals("Q2")
    return deals if whole_snapshot else deals[deals["period"] == CURRENT]


def _readings(fn: Callable[[pd.DataFrame], object], data: Data, either: bool) -> list[object]:
    """The reference under each acceptable reading of "current"."""
    if either:
        return [fn(_deals(data, True)), fn(_deals(data, False))]
    return [fn(_deals(data, False))]


def _close(a: object, b: object) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-6)
    return a == b


def _result(observed: Observed) -> object:
    fact = observed.answer.facts.get("result")
    return None if fact is None else fact.value


def scalar(fn: Callable[[pd.DataFrame], float], *, either: bool = True) -> Check:
    """The answer's single number matches the reference."""

    def check(observed: Observed, data: Data) -> list[str]:
        got = _result(observed)
        wanted = _readings(fn, data, either)
        if got is None or not any(_close(got, w) for w in wanted):
            return [f"result was {got!r}, expected one of {wanted!r}"]
        return []

    return check


def _mapping(table: pd.DataFrame, key: str) -> dict | None:
    if key not in table.columns or len(table.columns) < 2:
        return None
    value = [c for c in table.columns if c != key][-1]
    return {
        (None if pd.isna(k) else k): float(v)
        for k, v in zip(table[key], table[value])
    }


def grouped(key: str, fn: Callable[[pd.DataFrame], pd.Series], *, either: bool = True) -> Check:
    """The answer's table maps each `key` to the reference value."""

    def reference(frame: pd.DataFrame) -> dict:
        series = fn(frame)
        return {(None if pd.isna(k) else k): float(v) for k, v in series.items()}

    def check(observed: Observed, data: Data) -> list[str]:
        got = _mapping(observed.answer.table, key)
        wanted = _readings(reference, data, either)
        if got is None:
            return [f"table has no '{key}' column: {list(observed.answer.table.columns)}"]
        if not any(set(got) == set(w) and all(_close(got[k], w[k]) for k in w) for w in wanted):
            return [f"table was {got!r}, expected one of {wanted!r}"]
        return []

    return check


def top_value(column: str, fn: Callable[[pd.DataFrame], float], *, either: bool = True) -> Check:
    """The first row's `column` is the reference maximum."""

    def check(observed: Observed, data: Data) -> list[str]:
        table = observed.answer.table
        if column not in table.columns or table.empty:
            return [f"table has no '{column}' column: {list(table.columns)}"]
        got = float(table[column].iloc[0])
        wanted = _readings(fn, data, either)
        if not any(_close(got, w) for w in wanted):
            return [f"top {column} was {got}, expected one of {wanted}"]
        return []

    return check


def largest(column: str, fn: Callable[[pd.DataFrame], float], *, either: bool = True) -> Check:
    """The answer's single number, or its top row's `column` when it listed
    rows instead. "What's our biggest deal" is answered well either way."""

    def check(observed: Observed, data: Data) -> list[str]:
        if _result(observed) is not None:
            return scalar(fn, either=either)(observed, data)
        return top_value(column, fn, either=either)(observed, data)

    return check


def rows(count: int) -> Check:
    def check(observed: Observed, data: Data) -> list[str]:
        got = len(observed.answer.table)
        return [] if got == count else [f"{got} rows, expected {count}"]

    return check


def reason_mentions(text: str) -> Check:
    def check(observed: Observed, data: Data) -> list[str]:
        reason = getattr(observed.answer, "reason", "")
        return [] if text.lower() in reason.lower() else [f"reason doesn't mention {text!r}"]

    return check


# --- reference helpers ------------------------------------------------------


def _open(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["is_open"]]


def _won(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["is_won"]]


def _lost(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["is_lost"]]


def _in_june(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["close_date"].map(lambda d: d.year == 2026 and d.month == 6)]


# --- the cases --------------------------------------------------------------

CASES: tuple[Case, ...] = (
    # The metric lane: the router has to read the question right.
    Case("attainment-overall", "how are we tracking this quarter", "metric", (routed("attainment"),)),
    Case("attainment-segment", "how is the Enterprise segment doing this quarter", "metric",
         (routed("attainment", "segment", segment="Enterprise"),)),
    Case("attainment-rep", "how is Marcus Rivera tracking against quota", "metric",
         (routed("attainment", "rep", rep="Marcus Rivera"),)),
    Case("attainment-manager", "how is David Kim's team doing against quota", "metric",
         (routed("attainment", "manager", manager="David Kim"),)),
    Case("attainment-q1", "what was our attainment in Q1", "metric",
         (routed("attainment", period="Q1-2026"),)),
    Case("risk-overall", "which reps are at risk of missing Q2", "metric", (routed("risk"),)),
    Case("risk-rep", "is Sarah Chen at risk of missing quota this quarter", "metric",
         (routed("risk", "rep", rep="Sarah Chen"),)),
    Case("comparison", "how does this quarter compare to the same point in Q1", "metric",
         (routed("comparison", comparison_period="Q1-2026"),)),
    Case("product-mix", "how is our pipeline broken out by product line", "metric", (routed("product_mix"),)),
    Case("product-mix-best", "which product line is doing best this quarter", "metric", (routed("product_mix"),)),

    # The exploratory lane: the plan has to compute the right figures.
    Case("loss-reasons", "why are we losing deals", "exploratory",
         (grouped("loss_reason", lambda f: _lost(f).groupby("loss_reason", dropna=False).size()),)),
    Case("top-open-accounts", "which accounts have the most open pipeline", "exploratory",
         (top_value("sum_deal_value", lambda f: _open(f).groupby("account_name")["deal_value"].sum().max()),)),
    Case("avg-won-by-segment", "what's the average deal size of won deals by segment", "exploratory",
         (grouped("segment", lambda f: _won(f).groupby("segment")["deal_value"].mean()),)),
    Case("negotiation-count", "how many deals are in negotiation right now", "exploratory",
         (scalar(lambda f: len(f[f["stage"] == "Negotiation"])),)),
    Case("biggest-open-deals", "list our 5 biggest open deals", "exploratory",
         (rows(5), top_value("deal_value", lambda f: _open(f)["deal_value"].max()))),
    Case("lost-to-oracle", "how many deals have we lost to Oracle", "exploratory",
         (scalar(lambda f: len(f[f["loss_reason"] == "Competitor - Oracle"])),)),
    Case("open-by-stage", "how much open pipeline is sitting in each stage", "exploratory",
         (grouped("stage", lambda f: _open(f).groupby("stage")["deal_value"].sum()),)),
    Case("reps-per-manager", "how many reps does each manager have", "exploratory",
         (grouped("manager", lambda f: pd.Series({"David Kim": 4, "Lisa Huang": 4, "Carlos Reyes": 2}), either=False),)),
    Case("biggest-win-this-quarter", "what's the biggest deal we've won this quarter", "exploratory",
         (largest("deal_value", lambda f: _won(f)["deal_value"].max(), either=False),),
         note="'this quarter' should filter to the Q2 period, not the whole Q2 snapshot"),
    Case("closing-in-june", "how many deals are scheduled to close in June", "exploratory",
         (scalar(lambda f: len(_in_june(f))),)),

    # Refusals: nothing should be answered, and region never reaches a model.
    Case("region-word", "how is the West region doing this quarter", "refused",
         (no_generation, reason_mentions("region")), tags=("refused-topic",)),
    Case("territory-word", "which territory has the most pipeline", "refused",
         (no_generation,), tags=("refused-topic",)),
    Case("geography-paraphrase", "which part of the country has the most pipeline", "refused",
         tags=("refused-topic",), note="never says region, so only the generator's prompt stops it"),
    Case("geography-paraphrase-2", "where geographically are we strongest", "refused", tags=("refused-topic",)),
    Case("slack", "what did our Slack sentiment look like", "refused"),
    Case("forecast", "what will revenue be next year", "refused"),
    Case("off-topic", "what's the weather in Boston", "refused"),
    Case("unknown-period", "how did we do in Q3 2025", "refused"),
    Case("unsupported-grouping", "what's the risk picture by segment", "refused",
         note="risk exists but not by segment; answering it exploratorily would improvise a definition"),
    Case("ambiguous-lisa", "how is Lisa doing this quarter", "refused",
         note="Lisa Park is a rep and Lisa Huang is a manager"),
)
