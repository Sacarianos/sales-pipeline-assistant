"""Diffing the two snapshots into a change log and a divergence decomposition.

A plain outer join on `deal_id` reads a deal whose ID now points at a
different account as `unwon`, putting a fabricated revenue reversal on
screen with source rows sitting underneath it looking like evidence. ID
reuse is detected generically — both `account_name` and `created_date`
change for the same ID — and takes precedence over `unwon` and `drifted`
for that row, per ADR-0001. No deal ID is hardcoded anywhere in this module,
so it keeps working on next quarter's snapshot.

`reconcile` produces the change log: one row per deal per changed field,
carrying the deal ID, change type, field, and both snapshot values. It is
the audit trail — issue 06's secondary test seam, and the `changed_deals`
flag's source.

`divergence` produces the decomposition the snapshot-divergence flag reads:
what a naive stage-only join would have called `unwon`, split into the
deals that genuinely came unwon and the deals that only look unwon because
their ID was handed to a different account.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

CLOSED_WON = "Closed Won"
CLOSED_LOST = "Closed Lost"

# The raw fields diffed between snapshots for a matched deal. Derived columns
# the loader adds — period, is_won, is_open, and the joined rep attributes —
# are reconstructible from these and aren't diffed themselves.
DIFF_FIELDS = (
    "account_name",
    "segment",
    "region",
    "rep_id",
    "stage",
    "deal_value",
    "close_date",
    "created_date",
    "product_line",
    "loss_reason",
)

CHANGE_LOG_COLUMNS = ("deal_id", "change_type", "field", "q1_value", "q2_value")


def _is_reused(row: pd.Series) -> bool:
    return (
        row["account_name_q1"] != row["account_name_q2"]
        and row["created_date_q1"] != row["created_date_q2"]
    )


def _equal(a: object, b: object) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    return a == b


def _matched(q1: pd.DataFrame, q2: pd.DataFrame) -> pd.DataFrame:
    """Every deal_id present in both snapshots, columns suffixed `_q1`/`_q2`."""
    return q1.merge(q2, on="deal_id", suffixes=("_q1", "_q2"))


def _classify(row: pd.Series) -> str:
    """The change type for one matched deal, in precedence order.

    ID reuse is checked first and hides the row from `unwon` and `drifted`
    no matter what else differs — that precedence is the entire point of
    ADR-0001.
    """
    if _is_reused(row):
        return "id_reused"
    if row["stage_q1"] == CLOSED_WON and row["stage_q2"] != CLOSED_WON:
        return "unwon"
    if row["stage_q1"] == CLOSED_LOST and row["stage_q2"] not in (CLOSED_WON, CLOSED_LOST):
        return "reopened"
    if any(not _equal(row[f"{field}_q1"], row[f"{field}_q2"]) for field in DIFF_FIELDS):
        return "drifted"
    return "unchanged"


def reconcile(q1: pd.DataFrame, q2: pd.DataFrame) -> pd.DataFrame:
    """One row per deal per changed field, carrying the deal ID, change
    type, field, and both snapshot values.

    A deal that exists only in Q2 gets one row with `field` unset, since
    there is no Q1 record to diff a field against. A deal identical in both
    snapshots contributes no rows at all — nothing changed, so there's
    nothing to log.
    """
    q1_ids = set(q1["deal_id"])
    q2_ids = set(q2["deal_id"])

    rows: list[dict] = []
    for deal_id in sorted(q2_ids - q1_ids):
        rows.append(
            {
                "deal_id": deal_id,
                "change_type": "new_in_q2",
                "field": None,
                "q1_value": None,
                "q2_value": None,
            }
        )

    merged = _matched(q1, q2)
    for _, row in merged.iterrows():
        change_type = _classify(row)
        if change_type == "unchanged":
            continue
        for field in DIFF_FIELDS:
            a, b = row[f"{field}_q1"], row[f"{field}_q2"]
            if not _equal(a, b):
                rows.append(
                    {
                        "deal_id": row["deal_id"],
                        "change_type": change_type,
                        "field": field,
                        "q1_value": a,
                        "q2_value": b,
                    }
                )

    log = pd.DataFrame(rows, columns=list(CHANGE_LOG_COLUMNS))
    return log.sort_values(["deal_id", "field"], na_position="first").reset_index(drop=True)


@dataclass(frozen=True)
class Divergence:
    """The Q1 gap decomposed into what a naive join would misreport.

    `unwon_*` is the genuine unwins: closed won in Q1, not closed won in
    Q2, and not an ID reuse. `reused_unwon_*` is what a naive stage-only
    join would additionally have called unwon — deals that were never
    unwon at all, because the account behind that ID changed.
    """

    unwon_count: int
    unwon_value: float
    reused_unwon_count: int
    reused_unwon_value: float


def divergence(q1: pd.DataFrame, q2: pd.DataFrame) -> Divergence:
    merged = _matched(q1, q2)
    reused = merged.apply(_is_reused, axis=1)
    would_be_unwon = (merged["stage_q1"] == CLOSED_WON) & (merged["stage_q2"] != CLOSED_WON)

    genuine = merged[would_be_unwon & ~reused]
    reused_unwon = merged[would_be_unwon & reused]

    return Divergence(
        unwon_count=len(genuine),
        unwon_value=float(genuine["deal_value_q1"].sum()),
        reused_unwon_count=len(reused_unwon),
        reused_unwon_value=float(reused_unwon["deal_value_q1"].sum()),
    )


__all__ = ["CHANGE_LOG_COLUMNS", "DIFF_FIELDS", "Divergence", "divergence", "reconcile"]
