"""Issue 03: exploratory presentation.

The lane's flags, expression, and snapshot are asserted through the primary
seam, `ask(question, data, client)`, the same way issue 02's tests are. The
visual treatment itself - warning color, placement above the prose, no-click
expression - has no Streamlit test harness in this repo, so it's asserted the
same way `test_demo_readiness.py` asserts the sidebar wiring: against app.py's
own source rather than a rendered page.
"""

from __future__ import annotations

from pathlib import Path

from acme.domain import Answered
from acme.pipeline import ask
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (REPO_ROOT / "app.py").read_text(encoding="utf-8")


def test_data_quality_flags_still_run_on_an_exploratory_answer(data):
    """Partial period and stale close date are properties of the Q2
    snapshot, not of the lane that read it, so they still fire here the
    same way they do for a metric answer over the same snapshot."""
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={
            "expression": (
                "deals_q2[deals_q2['stage'] == 'Closed Lost']['loss_reason'].value_counts()"
            )
        },
    )
    answer = ask("why are we losing deals", data, client)

    assert isinstance(answer, Answered)
    kinds = {f.kind for f in answer.flags}
    assert {"partial_period", "stale_close_date"} <= kinds


def test_an_exploratory_answer_over_q1_flags_the_q1_snapshot_not_q2(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": "deals_q1['deal_value'].sum()"},
    )
    answer = ask("what was our total pipeline in Q1", data, client)

    assert isinstance(answer, Answered)
    assert answer.snapshot == "Q1"


def test_an_exploratory_answer_carries_its_expression(data):
    expression = "deals_q2['deal_value'].sum()"
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"expression": expression},
    )
    answer = ask("what's our total pipeline", data, client)

    assert isinstance(answer, Answered)
    assert answer.expression == expression


def test_the_warning_renders_before_the_prose_for_the_exploratory_lane():
    """`_render_answer` writes the red warning and the expression while
    still inside the `lane == "exploratory"` branch, ahead of the
    `st.write`/`write_stream` call that renders the prose - not after it."""
    lane_check = APP_SOURCE.index('answer.lane == "exploratory"')
    error_call = APP_SOURCE.index("st.error(EXPLORATORY_WARNING)")
    expression_call = APP_SOURCE.index("st.code(answer.expression")
    prose_call = APP_SOURCE.index("st.write_stream(_typewriter(answer.prose))")
    assert lane_check < error_call < expression_call < prose_call


def test_the_expression_is_never_behind_a_click():
    assert "st.expander" not in APP_SOURCE
    assert "st.popover" not in APP_SOURCE


def test_the_verified_metric_badge_is_gated_off_the_exploratory_lane():
    """The '✓ N figures verified' caption only ever renders in the branch
    that also checks the lane isn't exploratory, so a verified-metric badge
    can never appear on a generated-query answer."""
    badge_index = APP_SOURCE.index('f"✓ {answer.verified_figures} figures verified')
    guard_index = APP_SOURCE.rindex('elif answer.prose_source == "narrator"', 0, badge_index)
    exploratory_branch = APP_SOURCE.index('if answer.lane == "exploratory":\n        st.caption(EXPLORATORY_BADGE)')
    assert exploratory_branch < guard_index < badge_index
