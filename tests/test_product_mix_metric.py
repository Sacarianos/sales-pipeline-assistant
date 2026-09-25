"""Product mix: closed-won and open pipeline broken out by product line,
with no quota comparison, since quotas in this data are recorded per rep and
carry no product breakdown at all.

Per the parent spec's testing decisions, these go in through the primary
seam — a question string plus the loaded data — and assert on what reaches
the screen. Reference values are independently computed from the CSVs: Q2
closed-won splits 138,000 / 295,000 / 85,000 across Analytics Add-on, Core
Platform, and Security Module, summing to 518,000, which matches the
already-known org-wide Q2 closed-won total exactly.
"""

from __future__ import annotations

from acme.domain import Answered
from acme.pipeline import ask


def test_q2_closed_won_splits_by_product_line_and_sums_to_the_known_total(data):
    answer = ask("how is our pipeline broken out by product line", data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won_analytics_add_on"].value == 138_000
    assert answer.facts["closed_won_core_platform"].value == 295_000
    assert answer.facts["closed_won_security_module"].value == 85_000
    assert answer.facts["closed_won"].value == 518_000
    assert answer.facts["closed_won"].value == (
        answer.facts["closed_won_analytics_add_on"].value
        + answer.facts["closed_won_core_platform"].value
        + answer.facts["closed_won_security_module"].value
    )


def test_no_quota_or_attainment_fact_is_present(data):
    """This metric reports what closed and what's open. It never reports a
    percentage against quota, because no per-product quota exists to divide
    by — inventing one would be exactly the kind of unearned number this
    system's whole design argues against."""
    answer = ask("how is our pipeline broken out by product line", data)

    assert isinstance(answer, Answered)
    assert "quota" not in answer.facts
    assert not any("attainment" in key for key in answer.facts)


def test_product_line_attribution_flag_fires_and_names_the_real_assumption(data):
    answer = ask("how is our pipeline broken out by product line", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "product_line_attribution")
    assert "one product-line tag" in flag.lede
    assert "bundle" in flag.lede.lower()
    assert "does not confirm" in flag.lede


def test_q1_product_mix_answers_from_the_q1_snapshot(data):
    answer = ask("how was our pipeline broken out by product line in Q1", data)

    assert isinstance(answer, Answered)
    assert answer.intent.metric == "product_mix"
    assert answer.snapshot == "Q1"
    assert answer.facts["closed_won_core_platform"].value == 2_741_000
