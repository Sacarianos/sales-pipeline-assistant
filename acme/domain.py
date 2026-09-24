"""The contracts every layer of the assistant speaks in.

`Fact` is the only channel through which a number reaches prose. `Result` is
what a metric returns. `Answered` and `Refused` are what the query pipeline
returns, and are the only things the interface knows how to draw.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Union

import pandas as pd
from pydantic import BaseModel, Field


UNSUPPORTED = "unsupported"


class Unit(str, Enum):
    CURRENCY = "currency"
    PERCENT = "percent"
    COUNT = "count"
    DATE = "date"
    # A computed number with no pinned business meaning. The fallback lane
    # uses it when a query's result isn't a dollar figure or a count, like
    # the average of a column that isn't money.
    NUMBER = "number"


@dataclass(frozen=True)
class Fact:
    """A single named, computed value with a unit and a human label.

    The verifier reads only `value`. `unit` is what tells it that an 8 in
    "8 of 10 reps" is a count while 4.5 is a percent, and what scopes the
    thousands and millions shorthands to currency.
    """

    value: float
    unit: Unit
    label: str

    def formatted(self) -> str:
        if self.unit is Unit.CURRENCY:
            return f"{self.value:,.0f}"
        if self.unit is Unit.PERCENT:
            return f"{self.value:.1f}%"
        if self.unit is Unit.COUNT:
            return f"{self.value:,.0f}"
        if self.unit is Unit.NUMBER:
            if float(self.value).is_integer():
                return f"{self.value:,.0f}"
            return f"{self.value:,.2f}"
        return f"{self.value:.0f}"


class Intent(BaseModel):
    """The structured reading of a question.

    Issue 03 turns this model's JSON schema into the router's tool schema, so
    every field here is one the model will be asked to fill.
    """

    metric: str = Field(description="Metric name from the catalog, or 'unsupported'.")
    grouping: str = Field(
        default="overall",
        description=(
            "The scope the question asks about: 'overall', or one named segment, "
            "rep, or manager, with that name set in its own field. A question "
            "about every rep, like 'which reps are at risk', is 'overall'."
        ),
    )
    period: str = Field(description="Period key such as Q2-2026.")
    comparison_period: str | None = Field(default=None)
    segment: str | None = Field(default=None)
    rep: str | None = Field(default=None)
    manager: str | None = Field(default=None)
    restated: str = Field(description="One sentence restating how the question was read.")
    unsupported_reason: str | None = Field(default=None)
    # Why the metric is 'unsupported'. 'no_metric' means the data might answer
    # it but no registered metric does, so the exploratory lane may try.
    # 'ambiguous' means the question could mean more than one thing, so
    # nothing tries: guessing which is exactly the silent substitution this
    # system refuses.
    unsupported_kind: Literal["no_metric", "ambiguous"] | None = Field(default=None)

    def is_unsupported(self) -> bool:
        return self.metric == UNSUPPORTED


@dataclass(frozen=True)
class Result:
    """What a metric returns. Every field is displayed somewhere on screen."""

    facts: dict[str, Fact]
    table: pd.DataFrame
    source_rows: pd.DataFrame
    filters: dict[str, str]
    snapshot: str
    definition_keys: tuple[str, ...]
    template: str


@dataclass(frozen=True)
class Flag:
    """One assumption, caveat, or definition the answer rests on.

    `lede` is the sentence. `items` is the list that sentence introduces,
    where it introduces one, held as data rather than folded into the prose
    so the interface can lay a long list out as something readable instead of
    a paragraph of comma-separated IDs. `detail` puts the two back together
    and is what anything wanting the whole caveat as one string should read.
    """

    kind: str
    title: str
    lede: str
    items: tuple[str, ...] = ()

    @property
    def detail(self) -> str:
        if not self.items:
            return self.lede
        return f"{self.lede}: {', '.join(self.items)}."


@dataclass(frozen=True)
class Answered:
    """A question that was routed, validated, computed, flagged, and rendered."""

    kind: Literal["answered"] = field(default="answered", init=False)
    # "metric" for a registered metric's answer, "exploratory" for the
    # fallback lane's. One field on one variant rather than a parallel
    # Answered type, so every consumer that already handles an answer keeps
    # working and the interface decides what to draw from this alone.
    lane: Literal["metric", "exploratory"] = "metric"
    # Set only when `lane` is "exploratory". The query a model chose is the
    # one thing a reader can't otherwise check about this answer, so it
    # travels with the answer in two forms, both built from the query plan
    # and never from model prose. `query_description` is plain English for
    # the reader. `expression` is the equivalent pandas an analyst can paste
    # into a notebook to reproduce the figure.
    query_description: str = ""
    expression: str = ""
    # The one sentence restating how the question was read, rendered inside
    # the answer itself. For the metric lane this is `intent.restated`; the
    # fallback lane has no `Intent` (it never went through the router's
    # structured reading) but still owes the reader the same backstop
    # against a silent misroute, so it's a field every lane sets directly
    # rather than something derived only from `intent`.
    restated: str = ""
    prose: str = ""
    prose_source: Literal["narrator", "template"] = "template"
    verified_figures: int | None = None
    # True when the template is on screen because narration was attempted and
    # blocked — an API failure/timeout or a verification failure — rather
    # than because narration was never attempted (no client). Drives the
    # "blocked" badge, distinct from having no badge at all.
    narrator_blocked: bool = False
    # When verification blocked the narrator, its draft and the figures in it
    # that matched no fact. For diagnosis and evals, never drawn on screen.
    blocked_draft: str = ""
    unmatched_figures: tuple[str, ...] = ()
    facts: dict[str, Fact] = field(default_factory=dict)
    flags: tuple[Flag, ...] = ()
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_rows: pd.DataFrame = field(default_factory=pd.DataFrame)
    filters: dict[str, str] = field(default_factory=dict)
    snapshot: str = ""
    intent: Intent | None = None
    router_mode: Literal["online", "offline"] = "offline"

    @property
    def row_count(self) -> int:
        return len(self.source_rows)


@dataclass(frozen=True)
class Refused:
    """A question the system will not answer, with what it does cover."""

    kind: Literal["refused"] = field(default="refused", init=False)
    reason: str = ""
    hint: str = ""
    intent: Intent | None = None
    router_mode: Literal["online", "offline"] = "offline"


Answer = Union[Answered, Refused]
