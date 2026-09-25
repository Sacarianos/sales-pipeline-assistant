"""Issue 02: attainment across every grouping, with filter-agreement validation.

Per the testing decisions in the parent spec, these go in through the primary
seam — a question string plus the loaded data — and assert on what reaches the
screen. Reference values are independently computed from the CSVs and pinned in
the parent spec.
"""

from __future__ import annotations

from acme.domain import Answered, Refused
from acme.pipeline import ask


def test_enterprise_q2_headline_case(data):
    answer = ask("how is the Enterprise segment tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.intent.grouping == "segment"
    assert answer.facts["closed_won"].value == 165_000
    assert answer.facts["quota"].value == 3_650_000
    assert round(answer.facts["attainment_pct"].value, 1) == 4.5
    assert answer.facts["open_pipeline"].value == 3_600_000


def test_manager_grouping_matches_the_segment_it_owns(data):
    # David Kim manages exactly the Enterprise segment in this data, so the
    # manager-grouped answer should read identically to the segment-grouped one.
    by_manager = ask("how is David Kim's team tracking this quarter", data)
    by_segment = ask("how is the Enterprise segment tracking this quarter", data)

    assert isinstance(by_manager, Answered)
    assert isinstance(by_segment, Answered)
    assert by_manager.facts["closed_won"].value == by_segment.facts["closed_won"].value
    assert by_manager.facts["quota"].value == by_segment.facts["quota"].value


def test_rep_grouping_headline(data):
    answer = ask("how is Marcus Rivera tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won"].value == 0
    assert answer.facts["quota"].value == 850_000
    assert answer.facts["attainment_pct"].value == 0.0
    assert answer.facts["open_pipeline"].value == 1_125_000


def test_best_case_and_win_rate_weighted_exist_as_separate_facts(data):
    answer = ask("how is the Enterprise segment tracking this quarter", data)

    assert isinstance(answer, Answered)
    closed_won = answer.facts["closed_won"].value
    open_pipeline = answer.facts["open_pipeline"].value

    # best_case is never folded into attainment_pct: it sums closed-won and
    # open pipeline, a figure with no relationship to the attainment percentage.
    assert answer.facts["best_case"].value == closed_won + open_pipeline
    assert answer.facts["best_case"].value != answer.facts["attainment_pct"].value

    # win_rate_weighted scales open pipeline by the win rate, also untouched by
    # the attainment percentage.
    win_rate = answer.facts["win_rate_pct"].value
    expected_weighted = closed_won + open_pipeline * (win_rate / 100)
    assert round(answer.facts["win_rate_weighted"].value, 4) == round(
        expected_weighted, 4
    )


def test_rep_segment_conflict_refuses_naming_both(data):
    answer = ask(
        "how is Marcus Rivera tracking in the SMB segment this quarter", data
    )

    assert isinstance(answer, Refused)
    assert "Marcus Rivera" in answer.reason
    assert "SMB" in answer.reason


def test_small_sample_flag_on_a_headline_resting_on_few_deals(data):
    # Aisha Williams has 4 deals in Q2, below the five-deal threshold.
    answer = ask("how is Aisha Williams tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert answer.row_count == 4
    small_sample = next(f for f in answer.flags if f.kind == "small_sample")
    assert "4 deals" in small_sample.detail
