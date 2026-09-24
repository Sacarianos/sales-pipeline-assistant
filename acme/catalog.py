"""The catalog: the single source of truth for what the system can answer.

Built by walking the metric registry plus the loaded data. It feeds the router,
the validator, the refusal message, and the sidebar examples, so a metric that
registers itself is wired into all four without anyone touching them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .loading import Data
from .periods import PERIODS
from .registry import MetricSpec, registered

# The groupings the domain has words for. A metric declares which of them it
# actually answers at; the validator refuses the pairs nobody implemented yet.
GROUPINGS = ("overall", "segment", "rep", "manager")


@dataclass(frozen=True)
class Catalog:
    metrics: tuple[MetricSpec, ...]
    groupings: tuple[str, ...]
    segments: tuple[str, ...]
    reps: tuple[str, ...]
    managers: tuple[str, ...]
    regions: tuple[str, ...]
    periods: tuple[str, ...]
    as_of: date
    region_mismatch_count: int
    region_deal_count: int

    def metric_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.metrics)

    def metric(self, name: str) -> MetricSpec | None:
        for spec in self.metrics:
            if spec.name == name:
                return spec
        return None

    def supports(self, metric: str, grouping: str) -> bool:
        spec = self.metric(metric)
        return bool(spec and spec.supports(grouping))

    def examples(self) -> tuple[str, ...]:
        return tuple(q for spec in self.metrics for q in spec.examples)

    def coverage_hint(self) -> str:
        """What the system does cover, read off the catalog rather than written twice."""
        pairs = ", ".join(
            f"{spec.name} ({', '.join(spec.groupings)})" for spec in self.metrics
        )
        return (
            f"I can answer {pairs} for {' and '.join(self.periods)}, "
            f"as of {self.as_of}."
        )

    def region_refusal_reason(self) -> str:
        """Why region questions refuse, computed from the loaded data rather
        than quoted from a written string, so the number can't go stale."""
        return (
            "Region is out of scope: two definitions of region disagree in this "
            "data. Each deal carries its own region, and the rep who owns it "
            "carries a separate home region, and the two differ on "
            f"{self.region_mismatch_count} of {self.region_deal_count} deals in "
            "the current snapshot. Ask about segment, rep, or manager instead."
        )



def _ordered(values) -> tuple[str, ...]:
    return tuple(sorted({str(v) for v in values if str(v) != "nan"}))


def build_catalog(data: Data) -> Catalog:
    metrics = registered()
    groupings = list(GROUPINGS)
    for spec in metrics:
        for grouping in spec.groupings:
            if grouping not in groupings:
                groupings.append(grouping)

    return Catalog(
        metrics=metrics,
        groupings=tuple(groupings),
        segments=_ordered(data.reps["segment"]),
        reps=_ordered(data.reps["rep_name"]),
        managers=_ordered(data.reps["manager"]),
        regions=_ordered(data.reps["region"]),
        periods=PERIODS,
        as_of=data.as_of,
        region_mismatch_count=data.region_mismatch_count,
        region_deal_count=data.region_deal_count,
    )
