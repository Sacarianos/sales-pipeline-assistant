"""The chart layer introduces no number of its own.

Charts were out of scope in the original V1 cut, and the reason to let them
in is that they render figures the metrics already computed rather than
becoming a second place where a figure comes from. That claim is worth a
test rather than a comment, so this walks the data actually bound to every
chart and asserts each value traces back to a Fact, to a column of the
aggregate table the metric returned, or to the one declared threshold
constant the risk chart draws its reference line at.

Axis ticks and gridline labels are chrome drawn by Vega from the scale, not
data the view supplied, so they aren't in scope here. What's in scope is the
data the chart is bound to, which is the only thing this layer passes along.
"""

from __future__ import annotations

import pandas as pd
import pytest

from acme.charts import chart_for
from acme.domain import Answered
from acme.metrics.risk import RISK_THRESHOLD_PCT
from acme.pipeline import ask

QUESTIONS = [
    "how are we tracking this quarter",
    "which reps are at risk of missing Q2",
    "how does Q2 attainment compare to where we were at the same point in Q1",
]


def _bound_frames(chart) -> list[pd.DataFrame]:
    """Every DataFrame bound to `chart`, following layers."""
    frames: list[pd.DataFrame] = []
    data = getattr(chart, "data", None)
    if isinstance(data, pd.DataFrame):
        frames.append(data)
    layers = getattr(chart, "layer", None)
    if isinstance(layers, list):
        for layer in layers:
            frames.extend(_bound_frames(layer))
    return frames


def _numbers(frame: pd.DataFrame) -> list[float]:
    numeric = frame.select_dtypes(include="number")
    return [float(v) for v in numeric.to_numpy().flatten() if pd.notna(v)]


def _allowed(answer: Answered) -> set[float]:
    allowed = {float(fact.value) for fact in answer.facts.values()}
    allowed |= set(_numbers(answer.table))
    # The risk chart's reference line. A threshold is a rule the system
    # declares, not a figure it computed, and it is named in one place so it
    # can be allowed here explicitly instead of passing as a loose literal.
    allowed.add(float(RISK_THRESHOLD_PCT))
    return allowed


@pytest.mark.parametrize("question", QUESTIONS)
def test_every_charted_value_traces_back_to_a_fact_or_the_table(data, question):
    answer = ask(question, data)
    assert isinstance(answer, Answered)

    chart = chart_for(answer)
    assert chart is not None, f"expected a chart for {answer.intent.metric}"

    allowed = _allowed(answer)
    for frame in _bound_frames(chart):
        for value in _numbers(frame):
            assert any(abs(value - candidate) <= 1e-6 for candidate in allowed), (
                f"charted value {value} for '{question}' is not a Fact, a table "
                "column, or the declared risk threshold"
            )
