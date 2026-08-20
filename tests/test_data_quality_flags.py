"""Issue 05: data-quality flags that surface without being asked for.

Stale close date and missing field are asserted against the real Q2 snapshot,
using the reference counts pinned in the parent spec (two stale deals, one
closed-lost deal with no loss reason). Unknown stage has no naturally
occurring case in the shipped data, so that one test loads a small synthetic
snapshot through the real loader rather than reaching into the flag function
directly - the primary seam stays `ask(question, data, client)` either way.
"""

from __future__ import annotations

import pytest

from acme.domain import Answered
from acme.loading import load_data
from acme.pipeline import ask

REPS_CSV = (
    "rep_id,rep_name,segment,region,quota_q1_2026,quota_q2_2026,manager,hire_date\n"
    "REP-01,Test Rep,Enterprise,West,100000,100000,Test Manager,2020-01-01\n"
)

Q1_DEALS_CSV = (
    "deal_id,account_name,segment,region,rep_id,stage,deal_value,close_date,"
    "created_date,product_line,loss_reason\n"
    "OPP-Q1-1,Acme Co,Enterprise,West,REP-01,Closed Won,50000,2026-02-15,"
    "2025-11-01,Core Platform,\n"
)

Q2_DEALS_CSV = (
    "deal_id,account_name,segment,region,rep_id,stage,deal_value,close_date,"
    "created_date,product_line,loss_reason\n"
    "OPP-Q2-1,Nimbus LLC,Enterprise,West,REP-01,Verbal Commit,75000,2026-05-20,"
    "2026-02-01,Core Platform,\n"
)


@pytest.fixture
def synthetic_data(tmp_path):
    (tmp_path / "Q1").mkdir()
    (tmp_path / "Q2").mkdir()
    (tmp_path / "Q1" / "deals.csv").write_text(Q1_DEALS_CSV)
    (tmp_path / "Q2" / "deals.csv").write_text(Q2_DEALS_CSV)
    (tmp_path / "Q2" / "reps.csv").write_text(REPS_CSV)
    return load_data(data_dir=tmp_path)


def test_stale_close_date_flag_names_the_two_stale_deals(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "stale_close_date")
    assert "2 open deals" in flag.detail
    assert "OPP-066" in flag.detail
    assert "OPP-075" in flag.detail
    assert "2026-05-02" in flag.detail


def test_missing_field_flag_catches_the_closed_lost_deal_without_a_reason(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "missing_field")
    assert "1 closed-lost deal" in flag.detail
    assert "OPP-008" in flag.detail
    assert "Ironbridge" in flag.detail


def test_all_rules_run_and_their_flags_all_survive_together(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    kinds = {f.kind for f in answer.flags}
    # No rule short-circuits another: the partial-period, stale-close-date,
    # and missing-field conditions all hold at once for this answer, and all
    # three flags are present together.
    assert {"partial_period", "stale_close_date", "missing_field"} <= kinds


def test_unknown_stage_flag_fires_and_the_deal_still_counts_as_open(synthetic_data):
    answer = ask("how are we tracking this quarter", synthetic_data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "unknown_stage")
    assert "Verbal Commit" in flag.detail

    q2 = synthetic_data.deals("Q2")
    row = q2[q2["deal_id"] == "OPP-Q2-1"].iloc[0]
    assert row["is_open"]
    assert answer.facts["open_pipeline"].value == 75000
