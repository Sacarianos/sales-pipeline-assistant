"""A visual reading of figures the metric already computed.

Nothing here computes a number. Every value plotted is read straight from
`Answered.facts` or from the aggregate table the metric returned, so a chart
can only ever show a figure that already went through the same pandas
computation, and in the case of a fact, the same contract the verifier
checks prose against. A chart is a second rendering of the answer, never a
second source for it. `tests/test_charts.py` holds that rule to the numbers
rather than to this paragraph.

A metric with no builder registered here gets no chart at all, and the rest
of its answer renders exactly as before. That is what keeps "adding a metric
means editing exactly one file" true: a chart is an optional enhancement, not
part of a metric's wiring.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .domain import Answered
from .metrics.risk import RISK_THRESHOLD_PCT

CLEAR = "#1e8449"
AT_RISK = "#c0392b"
PRIMARY = "#2c6fbb"
MUTED = "#a8c4de"
RULE = "#5d6d7e"

# Every chart is drawn at the same height unless it scales with its rows,
# so the panel doesn't jump as answers change shape.
STANDARD_HEIGHT = 130
BAR_STEP = 26


def _fact(answer: Answered, key: str) -> float | None:
    fact = answer.facts.get(key)
    return None if fact is None else fact.value


def _threshold(value: float, label: str) -> alt.Chart:
    """A dashed reference line, for the quota or the risk threshold."""
    frame = pd.DataFrame([{"value": value, "label": label}])
    return (
        alt.Chart(frame)
        .mark_rule(color=RULE, strokeDash=[5, 4], size=2)
        .encode(x=alt.X("value:Q"), tooltip=[alt.Tooltip("label:N", title="")])
    )


def _attainment_chart(answer: Answered) -> alt.Chart | None:
    """Closed-won and best case as bars, with quota as the line either of
    them has to reach. The gap between the second bar and the line is the
    whole answer at a glance."""
    closed_won = _fact(answer, "closed_won")
    best_case = _fact(answer, "best_case")
    quota = _fact(answer, "quota")
    if closed_won is None or best_case is None or quota is None:
        return None

    order = ["Closed won", "Best case"]
    frame = pd.DataFrame(
        [
            {"measure": "Closed won", "value": closed_won},
            {"measure": "Best case", "value": best_case},
        ]
    )
    bars = (
        alt.Chart(frame)
        .mark_bar(size=26, cornerRadiusEnd=3)
        .encode(
            x=alt.X("value:Q", title=None, axis=alt.Axis(format="~s")),
            y=alt.Y("measure:N", sort=order, title=None),
            color=alt.Color(
                "measure:N",
                scale=alt.Scale(domain=order, range=[PRIMARY, MUTED]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("measure:N", title=""),
                alt.Tooltip("value:Q", title="Value", format=","),
            ],
        )
    )
    return (bars + _threshold(quota, "Quota")).properties(height=STANDARD_HEIGHT)


def _risk_chart(answer: Answered) -> alt.Chart | None:
    """Best-case coverage per rep against the 100 percent line. This is the
    one chart in the app that turns a sentence ("8 of 10 reps are below") into
    something readable in a glance, so it plots every rep in the table rather
    than only the ones prose is allowed to name."""
    table = answer.table
    if table.empty or not {"rep", "best_case_pct"}.issubset(table.columns):
        return None

    bars = (
        alt.Chart(table)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("best_case_pct:Q", title="Best-case coverage (%)"),
            y=alt.Y("rep:N", sort="-x", title=None),
            color=alt.condition(
                alt.datum.best_case_pct >= RISK_THRESHOLD_PCT,
                alt.value(CLEAR),
                alt.value(AT_RISK),
            ),
            tooltip=[
                alt.Tooltip("rep:N", title="Rep"),
                alt.Tooltip("best_case_pct:Q", title="Coverage %", format=".1f"),
                alt.Tooltip("best_case:Q", title="Best case", format=","),
                alt.Tooltip("quota:Q", title="Quota", format=","),
            ],
        )
    )
    height = max(STANDARD_HEIGHT, len(table) * BAR_STEP)
    return (bars + _threshold(RISK_THRESHOLD_PCT, "Quota")).properties(height=height)


def _comparison_chart(answer: Answered) -> alt.Chart | None:
    """The two sides of the comparison next to each other. Each bar is the
    attainment percentage its own snapshot produced, so this is the one place
    the two periods appear together without ever being blended."""
    current = _fact(answer, "attainment_pct")
    prior = _fact(answer, "comparison_attainment_pct")
    intent = answer.intent
    if current is None or prior is None or intent is None:
        return None
    if intent.comparison_period is None:
        return None

    frame = pd.DataFrame(
        [
            {"period": intent.comparison_period, "pct": prior, "which": "Comparison"},
            {"period": intent.period, "pct": current, "which": "Current"},
        ]
    )
    return (
        alt.Chart(frame)
        .mark_bar(size=26, cornerRadiusEnd=3)
        .encode(
            x=alt.X("pct:Q", title="Attainment against quota (%)"),
            y=alt.Y("period:N", sort=None, title=None),
            color=alt.Color(
                "which:N",
                scale=alt.Scale(domain=["Current", "Comparison"], range=[PRIMARY, MUTED]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("period:N", title="Period"),
                alt.Tooltip("pct:Q", title="Attainment %", format=".1f"),
            ],
        )
        .properties(height=STANDARD_HEIGHT)
    )


_BUILDERS = {
    "attainment": _attainment_chart,
    "risk": _risk_chart,
    "comparison": _comparison_chart,
}


def chart_for(answer: Answered) -> alt.Chart | None:
    """The chart for this answer, or None when there isn't one to draw.

    A chart is decoration over an answer that already stands on its own, so
    a builder that raises loses the chart and nothing else. The figures, the
    flags, the rows, and the trace are what the answer actually rests on, and
    none of them should ever come off screen because a bar failed to render.
    """
    if answer.intent is None:
        return None
    builder = _BUILDERS.get(answer.intent.metric)
    if builder is None:
        return None
    try:
        return builder(answer)
    except Exception:
        return None


__all__ = ["chart_for"]
