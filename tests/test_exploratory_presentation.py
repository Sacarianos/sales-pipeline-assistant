"""Issue 03: exploratory presentation.

The lane's flags, query, and snapshot, asserted through the primary seam,
`ask(question, data, client)`. What the reader sees on screen, the warning
above the prose and the query shown without a click, is tested by running
the app in `test_app.py`.
"""

from __future__ import annotations

from acme.domain import Answered
from acme.pipeline import ask
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input


def test_data_quality_flags_still_run_on_an_exploratory_answer(data):
    """Partial period and stale close date are properties of the Q2
    snapshot, not of the lane that read it, so they still fire here the
    same way they do for a metric answer over the same snapshot."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "frame": "deals_q2",
            "filters": [{"column": "stage", "op": "eq", "value": "Closed Lost"}],
            "group_by": ["loss_reason"],
            "aggregate": {"function": "count"},
        },
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    kinds = {f.kind for f in answer.flags}
    assert {"partial_period", "stale_close_date"} <= kinds


def test_an_exploratory_answer_over_q1_flags_the_q1_snapshot_not_q2(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q1", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    answer = ask("what was our total pipeline in Q1", data, client)

    assert isinstance(answer, Answered)
    assert answer.snapshot == "Q1"


def test_an_exploratory_answer_carries_its_query_in_english_and_in_pandas(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "sum", "column": "deal_value"}},
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.query_description == "Total deal value across deals in the Q2 snapshot."
    assert answer.expression == "deals_q2['deal_value'].sum()"
