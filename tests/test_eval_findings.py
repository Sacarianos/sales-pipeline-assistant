"""Regressions for what the first eval run against the real models found.

Each test here pins the system-side fix for one failed eval case. The eval
itself still has to be rerun to show the models behave, since a prompt rule
is a request, not a guarantee.
"""

from __future__ import annotations

from acme import fallback, router
from acme.catalog import build_catalog
from acme.domain import Answered, Fact, Intent, Refused, Unit
from acme.narrator import narrate
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


def test_the_intent_schema_says_a_breakdown_across_everyone_is_overall():
    description = Intent.model_json_schema()["properties"]["grouping"]["description"]
    assert "which reps are at risk" in description
    assert "overall" in description


def test_the_router_is_told_to_mark_a_metric_limit(data):
    """Eval case unsupported-grouping: "the risk picture by segment" was
    marked unsupported, fell through to the exploratory lane, and came back
    as open pipeline by segment, narrated as a risk concentration. Asking the
    router to name the metric anyway held for one run of the evals and then
    didn't, because the model kept stating the limit in its reason. So the
    limit gets its own kind, which the model uses on its own."""
    prompt = router._system_prompt(build_catalog(data))
    assert "metric_limit" in prompt


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


def test_a_metric_at_an_unsupported_grouping_refuses_without_generation(data):
    client = FallbackStubClient(
        router_input=dict(
            metric="risk", grouping="segment", segment="Enterprise", period="Q2-2026",
            restated="Reading this as risk for the Enterprise segment.",
        ),
        plan_input={"frame": "deals_q2", "aggregate": {"function": "count"}},
    )
    answer = ask("what's the risk picture for Enterprise", data, client)

    assert isinstance(answer, Refused)
    assert "does not answer at the 'segment' grouping" in answer.reason
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


def test_the_router_is_told_to_mark_ambiguity(data):
    prompt = router._system_prompt(build_catalog(data))
    assert "unsupported_kind" in prompt and "ambiguous" in prompt


def test_the_generator_is_told_not_to_pick_between_matching_names(data):
    prompt = fallback._system_prompt(data)
    assert "matches more than one" in prompt


def test_a_blocked_draft_is_kept_with_the_figures_that_failed():
    """The first eval run fell back to the template on 6 of 22 answers, and
    there was no way to see why. The blocked draft and its unmatched figures
    now travel with the answer, never to the screen."""
    facts = {"total": Fact(100.0, Unit.COUNT, "Total")}
    verification = verify("There are 100 deals, up 12 percent.", facts)
    assert verification.unmatched == ("12",)

    client = FallbackStubClient(router_input={}, narrator_text="There are 100 deals, up 12 percent.")
    narration = narrate("q", "r", facts, "There are 100 deals.", client)
    assert narration.blocked
    assert narration.prose == "There are 100 deals."
    assert narration.draft == "There are 100 deals, up 12 percent."
    assert narration.unmatched == ("12",)


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


def test_an_identifier_nobody_supplied_is_blocked():
    """Skipping identifiers outright would let the narrator name a deal that
    doesn't exist, so an identifier has to appear in a label or the
    restatement."""
    facts = {"row0": Fact(280000.0, Unit.CURRENCY, "OPP-079 / Sterling Analytics: deal_value")}
    verification = verify("OPP-999 leads at 280,000.", facts)
    assert not verification.ok
    assert verification.unmatched == ("OPP-999",)


def test_a_period_named_in_the_restatement_passes():
    facts = {"total": Fact(92.0, Unit.COUNT, "Rows the filters matched")}
    assert verify("In Q2-2026 there are 92 deals.", facts, context="Reading this for Q2-2026.").ok
    assert not verify("In Q3-2026 there are 92 deals.", facts, context="Reading this for Q2-2026.").ok


def test_the_generator_is_told_a_snapshot_is_not_a_quarter(data):
    """Eval case biggest-win-this-quarter: three runs out of three read the
    whole Q2 snapshot for "this quarter" and reported a deal that closed in
    Q1, with a draft claiming it closed in Q2."""
    prompt = fallback._system_prompt(data)
    assert "this quarter" in prompt
    assert "filter period" in prompt
