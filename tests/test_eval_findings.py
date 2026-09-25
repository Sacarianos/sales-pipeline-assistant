"""Regressions for what the first eval run against the real models found.

Each test here pins the system-side fix for one failed eval case. The eval
itself still has to be rerun to show the models behave, since a prompt rule
is a request, not a guarantee.
"""

from __future__ import annotations

from acme import fallback
from acme.domain import Answered, Fact, Refused, Unit
from acme.pipeline import ask
from acme.verifier import verify
from tests.test_fallback_lane import FallbackStubClient, _unsupported_input
from tests.test_llm_router_and_refusals import StubRouterClient


def test_a_named_grouping_without_its_name_refuses(data):
    """Eval case risk-overall: "which reps are at risk" came back with
    grouping 'rep' and no rep named. The answer happened to be right, but a
    contradictory intent shouldn't be computed on a guess."""
    client = StubRouterClient(
        tool_input=dict(metric="risk", grouping="rep", period="Q2-2026", restated="Reading this as risk by rep.")
    )
    answer = ask("which reps are at risk of missing Q2", data, client)

    assert isinstance(answer, Refused)
    assert "grouping 'rep' needs a named rep" in answer.reason


def test_a_metric_limit_refuses_without_generation(data):
    client = FallbackStubClient(
        router_input=_unsupported_input("risk answers overall or by rep, not by segment")
        | {"unsupported_kind": "metric_limit"},
        plan_input={"frame": "deals_q2", "aggregate": {"function": "count"}},
    )
    answer = ask("what's the risk picture by segment", data, client)

    assert isinstance(answer, Refused)
    assert "not by segment" in answer.reason
    assert fallback.TOOL_NAME not in [c["tools"][0]["name"] for c in client.calls if c.get("tools")]


def test_an_ambiguous_question_refuses_without_generation(data):
    """Eval case ambiguous-lisa: "how is Lisa doing" matches the rep Lisa
    Park and the manager Lisa Huang, and the generator silently picked the
    rep. An ambiguous reading refuses and says why."""
    client = FallbackStubClient(
        router_input=_unsupported_input("'Lisa' could be the rep Lisa Park or the manager Lisa Huang")
        | {"unsupported_kind": "ambiguous"},
        plan_input={"frame": "deals_q2", "aggregate": {"function": "count"}},
    )
    answer = ask("how is Lisa doing this quarter", data, client)

    assert isinstance(answer, Refused)
    assert "Lisa Park" in answer.reason
    assert fallback.TOOL_NAME not in [c["tools"][0]["name"] for c in client.calls if c.get("tools")]


def test_an_answer_carries_its_blocked_draft(data):
    client = FallbackStubClient(
        router_input=_unsupported_input(),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "count"}},
        narrator_text="We have 92 deals, 40 percent of them won.",
    )
    answer = ask("how many deals do we have", data, client)

    assert isinstance(answer, Answered)
    assert answer.narrator_blocked
    assert answer.blocked_draft == "We have 92 deals, 40 percent of them won."
    assert answer.unmatched_figures == ("40",)


def test_an_identifier_named_in_a_fact_label_is_not_read_as_a_figure():
    """Eval case biggest-open-deals: every listing was blocked because
    "OPP-079" read as the number 79."""
    facts = {"row0": Fact(280000.0, Unit.CURRENCY, "OPP-079 / Sterling Analytics: deal_value")}
    verification = verify("OPP-079 with Sterling Analytics leads at 280,000.", facts)
    assert verification.ok
    assert verification.verified_count == 1

    # A period counts when the restatement names it, and only then.
    counted = {"total": Fact(92.0, Unit.COUNT, "Rows the filters matched")}
    assert verify("In Q2-2026 there are 92 deals.", counted, context="Reading this for Q2-2026.").ok
    assert not verify("In Q3-2026 there are 92 deals.", counted, context="Reading this for Q2-2026.").ok


def test_an_identifier_nobody_supplied_is_blocked():
    """Skipping identifiers outright would let the narrator name a deal that
    doesn't exist, so an identifier has to appear in a label or the
    restatement."""
    facts = {"row0": Fact(280000.0, Unit.CURRENCY, "OPP-079 / Sterling Analytics: deal_value")}
    verification = verify("OPP-999 leads at 280,000.", facts)
    assert not verification.ok
    assert verification.unmatched == ("OPP-999",)
