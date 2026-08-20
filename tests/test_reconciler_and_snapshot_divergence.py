"""Issue 06: the reconciler, Q1 snapshot routing, and divergence disclosure.

Per the parent spec's testing decisions, the reconciliation matrix is the one
deliberate exception to the external-behavior rule: ID reuse detection is the
highest-risk logic in the system, and getting it wrong reproduces the exact
failure the whole project exists to prevent, so it's tested head on against
`data.change_log` and `data.divergence` rather than only inferred through the
primary seam. Everything else here goes in through `ask(question, data)` and
asserts on what reaches the screen, per the usual rule.

All reference counts below were independently computed from
`data/Q1/deals.csv` and `data/Q2/deals.csv` (see the merge-and-classify
scripts run during implementation), not copied from the issue text
unverified. One number in the issue checklist doesn't hold up against the
data: it says one deal reopens, but three non-reused deals go from
`Closed Lost` in Q1 to an open stage in Q2 with nothing else about them
special (OPP-010, OPP-032, OPP-054) — all three satisfy CONTEXT.md's own
definition of `reopened` ("Closed Lost in Q1, an open stage in Q2"). Pinning
the test to the issue's "one" would mean hardcoding two of those three out of
the classification, which is exactly the kind of hand-maintained exception
ADR-0001 exists to avoid. This suite asserts the generically-computed value.
"""

from __future__ import annotations

import pytest

from acme.domain import Answered
from acme.loading import load_data
from acme.pipeline import ask

REPS_CSV = (
    "rep_id,rep_name,segment,region,quota_q1_2026,quota_q2_2026,manager,hire_date\n"
    "REP-01,Steady Rep,Enterprise,West,100000,100000,Test Manager,2020-01-01\n"
    "REP-02,Changed Rep,Enterprise,West,100000,100000,Test Manager,2020-01-01\n"
)

# Steady Rep's Q1 deal is byte-identical across both snapshots. Changed Rep's
# Q1 deal comes unwon in Q2 — the same deal ID, only the stage differs.
Q1_DEALS_CSV = (
    "deal_id,account_name,segment,region,rep_id,stage,deal_value,close_date,"
    "created_date,product_line,loss_reason\n"
    "OPP-STEADY,Anchor Co,Enterprise,West,REP-01,Closed Won,40000,2026-02-01,"
    "2025-11-01,Core Platform,\n"
    "OPP-CHANGED,Drift Co,Enterprise,West,REP-02,Closed Won,30000,2026-02-01,"
    "2025-11-01,Core Platform,\n"
)

Q2_DEALS_CSV = (
    "deal_id,account_name,segment,region,rep_id,stage,deal_value,close_date,"
    "created_date,product_line,loss_reason\n"
    "OPP-STEADY,Anchor Co,Enterprise,West,REP-01,Closed Won,40000,2026-02-01,"
    "2025-11-01,Core Platform,\n"
    "OPP-CHANGED,Drift Co,Enterprise,West,REP-02,Closed Lost,30000,2026-02-01,"
    "2025-11-01,Core Platform,No budget\n"
)


@pytest.fixture
def steady_and_changed_data(tmp_path):
    (tmp_path / "Q1").mkdir()
    (tmp_path / "Q2").mkdir()
    (tmp_path / "Q1" / "deals.csv").write_text(Q1_DEALS_CSV)
    (tmp_path / "Q2" / "deals.csv").write_text(Q2_DEALS_CSV)
    (tmp_path / "Q2" / "reps.csv").write_text(REPS_CSV)
    return load_data(data_dir=tmp_path)


def test_thirteen_ids_classify_as_reused(data):
    reused = data.change_log[data.change_log["change_type"] == "id_reused"]
    assert reused["deal_id"].nunique() == 13


def test_twelve_reused_ids_would_otherwise_classify_as_unwon(data):
    assert data.divergence.reused_unwon_count == 12
    assert data.divergence.reused_unwon_value == 1_220_000


def test_four_deals_are_genuine_unwins_worth_363000(data):
    assert data.divergence.unwon_count == 4
    assert data.divergence.unwon_value == 363_000


def test_reused_deal_ids_are_not_reported_as_unwon(data):
    unwon = set(data.change_log.loc[data.change_log["change_type"] == "unwon", "deal_id"])
    reused = set(data.change_log.loc[data.change_log["change_type"] == "id_reused", "deal_id"])
    assert not (unwon & reused)


def test_four_deals_classify_as_new_in_q2(data):
    new_in_q2 = data.change_log[data.change_log["change_type"] == "new_in_q2"]
    assert new_in_q2["deal_id"].nunique() == 4


def test_reopened_deals_are_closed_lost_in_q1_and_open_in_q2(data):
    reopened = set(data.change_log.loc[data.change_log["change_type"] == "reopened", "deal_id"])
    # See the module docstring: three deals meet the generic reopened rule,
    # not the one the issue names.
    assert reopened == {"OPP-010", "OPP-032", "OPP-054"}


def test_one_value_drift_exists_outside_the_reused_set(data):
    reused = set(data.change_log.loc[data.change_log["change_type"] == "id_reused", "deal_id"])
    value_drift = data.change_log[
        (data.change_log["field"] == "deal_value") & (~data.change_log["deal_id"].isin(reused))
    ]
    assert list(value_drift["deal_id"]) == ["OPP-021"]
    row = value_drift.iloc[0]
    assert row["q1_value"] == 155_000
    assert row["q2_value"] == 120_000


def test_region_drift_is_detected_outside_the_reused_set(data):
    reused = set(data.change_log.loc[data.change_log["change_type"] == "id_reused", "deal_id"])
    region_drift = data.change_log[
        (data.change_log["field"] == "region") & (~data.change_log["deal_id"].isin(reused))
    ]
    assert list(region_drift["deal_id"]) == ["OPP-003"]
    row = region_drift.iloc[0]
    assert row["q1_value"] == "West"
    assert row["q2_value"] == "Central"


def test_no_deal_id_is_hardcoded_in_the_reconciler_module():
    import inspect

    from acme import reconciler

    source = inspect.getsource(reconciler)
    assert "OPP-" not in source


def test_q1_closed_won_leads_as_reported_with_restated_alongside(data):
    answer = ask("how were we tracking in Q1", data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won"].value == 6_041_000
    assert round(answer.facts["attainment_pct"].value, 1) == 102.0
    assert answer.facts["restated_closed_won"].value == 4_050_000
    assert round(answer.facts["restated_attainment_pct"].value, 1) == 68.4


def test_divergence_flag_decomposes_the_gap_into_unwins_and_reused_ids(data):
    answer = ask("how were we tracking in Q1", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "snapshot_divergence")
    assert "1,991,000" in flag.detail
    assert "4 deals worth 363,000" in flag.detail
    assert "12 deal IDs worth 1,220,000" in flag.detail


def test_divergence_flag_absent_from_a_q2_question(data):
    answer = ask("how are we tracking this quarter", data)

    assert isinstance(answer, Answered)
    assert not [f for f in answer.flags if f.kind == "snapshot_divergence"]


def test_divergence_flag_absent_when_scoped_below_overall(data):
    # The decomposition counts describe the whole Q1 portfolio; a
    # segment-scoped Q1 question restates its own slice but doesn't get the
    # organization-wide breakdown attached to it.
    answer = ask("how was the Enterprise segment tracking in Q1", data)

    assert isinstance(answer, Answered)
    assert answer.intent.grouping == "segment"
    assert not [f for f in answer.flags if f.kind == "snapshot_divergence"]


def test_changed_deals_flag_names_deals_that_changed_between_snapshots(data):
    answer = ask("how were we tracking in Q1", data)

    assert isinstance(answer, Answered)
    flag = next(f for f in answer.flags if f.kind == "changed_deals")
    assert "OPP-076 (id_reused)" in flag.detail
    assert "OPP-020 (unwon)" in flag.detail


def test_no_answer_compares_a_stage_across_snapshots(data):
    # Stage is reported only within the snapshot that owns it. Nothing in
    # the fact set, table, or restated Q1 answer names a Q1 stage and a Q2
    # stage together.
    answer = ask("how were we tracking in Q1", data)

    assert isinstance(answer, Answered)
    assert not any("stage" in key for key in answer.facts)
    assert "stage" not in answer.table.columns


def test_restated_omitted_for_a_rep_slice_reconciliation_never_touched(
    steady_and_changed_data,
):
    # The parent spec shows restated "alongside" as-reported only when the
    # two differ. Steady Rep's Q1 deal is identical in both snapshots, so
    # restating their own slice would just repeat the as-reported number.
    answer = ask("how is Steady Rep tracking in Q1", steady_and_changed_data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won"].value == 40_000
    assert "restated_closed_won" not in answer.facts
    assert "restated" not in answer.prose.lower()


def test_restated_present_for_a_rep_slice_reconciliation_did_touch(
    steady_and_changed_data,
):
    answer = ask("how is Changed Rep tracking in Q1", steady_and_changed_data)

    assert isinstance(answer, Answered)
    assert answer.facts["closed_won"].value == 30_000
    assert answer.facts["restated_closed_won"].value == 0
