"""Issue 01: the spine from a question string to a computed answer on screen.

Per the testing decisions in the parent spec, a good test here goes in through
the primary seam — a question string plus the loaded data — and asserts on
what reaches the screen. It does not reach into a metric function, a flag
rule, or the router directly.
"""

from __future__ import annotations

from acme.catalog import build_catalog
from acme.domain import Answered, Fact, Refused, Result, Unit
from acme.loading import quota_total
from acme.pipeline import ask


def test_current_quarter_no_metric_named_returns_headline_attainment(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won"].value == 518_000
    assert answer.facts["quota"].value == 6_200_000
    assert round(answer.facts["attainment_pct"].value, 1) == 8.4


def test_restatement_renders_inside_the_answer_not_only_the_trace(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.restated
    # The restatement is folded into the prose itself, matching ADR-0005: a
    # question naming no quarter says so in the sentence a human reads.
    assert "Q2-2026" in answer.restated
    assert "named no quarter" in answer.restated


def test_offline_router_produces_a_valid_intent_with_a_restatement(data):
    answer = ask("how are we tracking this quarter", data)

    assert answer.router_mode == "offline"
    assert answer.intent is not None
    assert answer.intent.metric == "attainment"
    assert answer.intent.period == "Q2-2026"
    assert answer.intent.restated


def test_fact_carries_value_unit_and_label():
    fact = Fact(value=8.4, unit=Unit.PERCENT, label="Attainment against quota")
    assert fact.value == 8.4
    assert fact.unit is Unit.PERCENT
    assert fact.label == "Attainment against quota"


def test_result_carries_the_full_contract(data):
    answer = ask("how are we tracking this quarter", data)
    assert isinstance(answer, Answered)

    # Everything Result promises is reachable off the Answered variant.
    assert answer.facts
    assert not answer.table.empty
    assert not answer.source_rows.empty
    assert answer.filters
    assert answer.snapshot == "Q2"
    assert answer.intent is not None


def test_period_membership_uses_close_date_for_open_and_closed_deals(data):
    # Named in the parent spec: the Q1 snapshot's 25 open deals all carry Q2
    # close dates, and the Q2 snapshot carries 40 deals (closed, by the time
    # of that snapshot) with Q1 close dates. Both get their period from
    # close_date alone, not from stage or from being open vs. closed.
    q1 = data.deals("Q1")
    open_with_q2_close_date = q1[(q1["period"] == "Q2-2026") & q1["is_open"]]
    assert len(open_with_q2_close_date) == 25

    q2 = data.deals("Q2")
    rows_with_q1_close_date = q2[q2["period"] == "Q1-2026"]
    assert len(rows_with_q1_close_date) == 40


def test_open_is_the_complement_of_closed_won_and_closed_lost(data):
    q2 = data.deals("Q2")
    stages_marked_open = set(q2.loc[q2["is_open"], "stage"])
    assert "Closed Won" not in stages_marked_open
    assert "Closed Lost" not in stages_marked_open
    # Q2 uses Negotiation, a stage name Q1 never had, and it must still read
    # as open through the complement rule rather than a stale whitelist.
    assert "Negotiation" in stages_marked_open


def test_catalog_is_built_from_registry_plus_data(data):
    catalog = build_catalog(data)

    assert "attainment" in catalog.metric_names()
    assert catalog.groupings
    assert catalog.segments
    assert catalog.reps
    assert catalog.managers
    assert catalog.periods == ("Q1-2026", "Q2-2026")
    assert catalog.as_of == data.as_of


def test_adding_a_metric_only_requires_the_registered_spec_to_exist(data):
    catalog = build_catalog(data)
    spec = catalog.metric("attainment")

    assert spec is not None
    assert spec.groupings
    assert spec.intent_fields
    assert spec.definition_keys
    assert spec.examples
    assert callable(spec.compute)


def test_flags_panel_renders_partial_period_and_definition(data):
    answer = ask("how are we tracking this quarter", data)
    assert isinstance(answer, Answered)

    partial = next(f for f in answer.flags if f.kind == "partial_period")
    assert "day 32 of 91" in partial.detail
    assert "2026-05-02" in partial.detail

    definition = next(f for f in answer.flags if f.kind == "definition:attainment")
    assert "closed-won revenue" in definition.detail.lower()
    assert "quota" in definition.detail.lower()


def test_four_panel_sections_have_something_to_render(data):
    answer = ask("how are we tracking this quarter", data)
    assert isinstance(answer, Answered)

    assert answer.facts               # figures
    assert answer.flags                # flags
    assert answer.row_count > 0        # source rows, with a count
    assert answer.filters              # the filter that produced them
    assert answer.intent is not None   # trace: intent
    assert answer.snapshot             # trace: answering snapshot


def test_quarterly_quota_totals(data):
    assert quota_total(data.quotas, "Q1-2026") == 5_920_000
    assert quota_total(data.quotas, "Q2-2026") == 6_200_000


def test_unsupported_question_refuses_with_a_hint(data):
    answer = ask("what did our Slack sentiment look like", data)

    assert isinstance(answer, Refused)
    assert answer.reason
    assert answer.hint
    assert "attainment" in answer.hint
