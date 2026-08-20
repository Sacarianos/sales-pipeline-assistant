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
        return f"{self.value:.0f}"


class Intent(BaseModel):
    """The structured reading of a question.

    Issue 03 turns this model's JSON schema into the router's tool schema, so
    every field here is one the model will be asked to fill.
    """

    metric: str = Field(description="Metric name from the catalog, or 'unsupported'.")
    grouping: str = Field(default="overall", description="overall, segment, rep, or manager.")
    period: str = Field(description="Period key such as Q2-2026.")
    comparison_period: str | None = Field(default=None)
    segment: str | None = Field(default=None)
    rep: str | None = Field(default=None)
    manager: str | None = Field(default=None)
    restated: str = Field(description="One sentence restating how the question was read.")
    unsupported_reason: str | None = Field(default=None)

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
    """One assumption, caveat, or definition the answer rests on."""

    kind: str
    title: str
    detail: str


@dataclass(frozen=True)
class Answered:
    """A question that was routed, validated, computed, flagged, and rendered."""

    kind: Literal["answered"] = field(default="answered", init=False)
    prose: str = ""
    # "template" until the narrator arrives in issue 04.
    prose_source: Literal["narrator", "template"] = "template"
    verified_figures: int | None = None
    facts: dict[str, Fact] = field(default_factory=dict)
    flags: tuple[Flag, ...] = ()
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_rows: pd.DataFrame = field(default_factory=pd.DataFrame)
    filters: dict[str, str] = field(default_factory=dict)
    snapshot: str = ""
    intent: Intent | None = None
    router_mode: Literal["online", "offline"] = "offline"

    @property
    def restated(self) -> str:
        return self.intent.restated if self.intent else ""

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
