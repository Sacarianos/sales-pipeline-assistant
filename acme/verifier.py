"""Checking every numeric token the narrator wrote against the facts it was
handed.

Every numeric token is pulled out of the prose, stripped of currency symbols,
thousands separators, and percent signs, and compared against an allowed set
built from the facts plus their honest variants, within a small tolerance.
No token is exempt by pattern — a number that belongs in prose but isn't a
metric output, such as the period year, is supplied to the narrator as a fact
rather than carved out of this check (see ADR-0003).

Variant generation never changes a value's magnitude. A currency fact gets a
rounding to the nearest whole dollar and nothing else, which absorbs float
summation noise without ever admitting a thousands or millions shorthand —
letting "1,991" verify against a 1,991,000 fact is exactly the imprecision
this module exists to catch. Percent, count, and date facts additionally
round to one and two decimals, since their prose form is more often a
rounded percentage or a whole count than the underlying float.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .domain import Fact, Unit

NUMBER_TOKEN = re.compile(r"\$?\b\d[\d,]*(?:\.\d+)?%?")

TOLERANCE = 1e-6


@dataclass(frozen=True)
class Verification:
    ok: bool
    verified_count: int


def _extract_tokens(prose: str) -> list[float]:
    tokens = []
    for raw in NUMBER_TOKEN.findall(prose):
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "")
        if cleaned and cleaned != ".":
            tokens.append(float(cleaned))
    return tokens


def _variants(fact: Fact) -> set[float]:
    variants = {fact.value, round(fact.value, 0)}
    if fact.unit is not Unit.CURRENCY:
        variants.add(round(fact.value, 1))
        variants.add(round(fact.value, 2))
    return variants


def _allowed_values(facts: dict[str, Fact]) -> set[float]:
    allowed: set[float] = set()
    for fact in facts.values():
        allowed |= _variants(fact)
    return allowed


def _matches(token: float, allowed: set[float]) -> bool:
    return any(abs(token - value) <= TOLERANCE for value in allowed)


def verify(prose: str, facts: dict[str, Fact]) -> Verification:
    """Every numeric token in `prose` must match a fact or an honest variant
    of one. A single mismatch fails the whole paragraph — the caller falls
    back to the deterministic template rather than publishing anything
    partially wrong."""
    tokens = _extract_tokens(prose)
    allowed = _allowed_values(facts)
    for token in tokens:
        if not _matches(token, allowed):
            return Verification(ok=False, verified_count=0)
    return Verification(ok=True, verified_count=len(tokens))
