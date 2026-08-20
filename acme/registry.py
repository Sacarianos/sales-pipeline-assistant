"""The metric registry and its decorator.

A metric is one self-describing module that registers itself. The registry is
what the catalog walks, which is in turn what the router prompt, the validator,
the refusal message, and the sidebar examples are all built from. Adding a
metric means dropping one file into `acme/metrics/` and editing nothing
else.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .domain import Intent, Result
from .loading import Data


@dataclass(frozen=True)
class MetricRequest:
    """Everything a metric computation is allowed to see."""

    intent: Intent
    data: Data
    as_of: date


Computation = Callable[[MetricRequest], Result]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    description: str
    groupings: tuple[str, ...]
    intent_fields: tuple[str, ...]
    definition_keys: tuple[str, ...]
    examples: tuple[str, ...]
    compute: Computation

    def supports(self, grouping: str) -> bool:
        return grouping in self.groupings


_REGISTRY: dict[str, MetricSpec] = {}


def metric(
    *,
    name: str,
    description: str,
    groupings: tuple[str, ...],
    intent_fields: tuple[str, ...],
    definition_keys: tuple[str, ...],
    examples: tuple[str, ...],
) -> Callable[[Computation], Computation]:
    """Register a metric computation under `name`."""

    def register(compute: Computation) -> Computation:
        _REGISTRY[name] = MetricSpec(
            name=name,
            description=description,
            groupings=groupings,
            intent_fields=intent_fields,
            definition_keys=definition_keys,
            examples=examples,
            compute=compute,
        )
        return compute

    return register


def discover() -> None:
    """Import every module under `acme.metrics` so it can register itself."""
    package = importlib.import_module("acme.metrics")
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"acme.metrics.{module.name}")


def registered() -> tuple[MetricSpec, ...]:
    discover()
    return tuple(_REGISTRY[name] for name in sorted(_REGISTRY))


def get(name: str) -> MetricSpec | None:
    discover()
    return _REGISTRY.get(name)
