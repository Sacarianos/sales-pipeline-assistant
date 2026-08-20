"""Load time: read the snapshots and the quota source once, and normalize them.

Runs once and is cached. It parses dates, normalizes stage strings, melts the
quota columns into one row per rep per period, and joins rep attributes onto
deals. Nothing here depends on a question.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from . import config
from .periods import PERIODS, period_of

CLOSED_WON = "Closed Won"
CLOSED_LOST = "Closed Lost"

# The only two stage names the system hardcodes. Open is the complement of
# these two, never a maintained list of open-stage names.
CLOSED_STAGES = (CLOSED_WON, CLOSED_LOST)

# Known solely so the loader can raise an unknown-stage flag when it meets a
# name it has not been told about. Never used to decide what counts as open.
KNOWN_STAGES = (
    "Prospecting",
    "Discovery",
    "Proposal",
    "Negotiation",
    CLOSED_WON,
    CLOSED_LOST,
)

QUOTA_COLUMNS = {"quota_q1_2026": "Q1-2026", "quota_q2_2026": "Q2-2026"}

REP_ATTRIBUTES = ["rep_id", "rep_name", "manager", "rep_segment", "rep_region"]


@dataclass(frozen=True)
class Data:
    """Everything load time produced, handed whole to query time."""

    snapshots: dict[str, pd.DataFrame]
    quotas: pd.DataFrame
    reps: pd.DataFrame
    unknown_stages: tuple[str, ...]
    as_of: date

    def deals(self, snapshot: str) -> pd.DataFrame:
        return self.snapshots[snapshot]


def normalize_stage(raw: object) -> str:
    """Collapse whitespace and casing onto a known stage name where one matches."""
    text = " ".join(str(raw).split())
    for known in KNOWN_STAGES:
        if text.casefold() == known.casefold():
            return known
    return text


def _read_reps(path: Path) -> pd.DataFrame:
    reps = pd.read_csv(path)
    reps["hire_date"] = pd.to_datetime(reps["hire_date"]).dt.date
    return reps


def melt_quotas(reps: pd.DataFrame) -> pd.DataFrame:
    """One row per rep per period, from the wide quota columns."""
    present = [c for c in QUOTA_COLUMNS if c in reps.columns]
    melted = reps.melt(
        id_vars=["rep_id", "rep_name", "segment", "manager"],
        value_vars=present,
        var_name="quota_column",
        value_name="quota",
    )
    melted["period"] = melted["quota_column"].map(QUOTA_COLUMNS)
    melted = melted.drop(columns=["quota_column"])
    melted["quota"] = melted["quota"].astype(float)
    return melted[["rep_id", "rep_name", "segment", "manager", "period", "quota"]]


def _load_snapshot(path: Path, reps: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    deals = pd.read_csv(path)
    for column in ("close_date", "created_date"):
        deals[column] = pd.to_datetime(deals[column]).dt.date

    deals["stage"] = deals["stage"].map(normalize_stage)
    unknown = {s for s in deals["stage"].unique() if s not in KNOWN_STAGES}

    deals["period"] = deals["close_date"].map(period_of)
    deals["is_won"] = deals["stage"] == CLOSED_WON
    deals["is_lost"] = deals["stage"] == CLOSED_LOST
    deals["is_open"] = ~deals["stage"].isin(CLOSED_STAGES)
    deals["deal_value"] = deals["deal_value"].astype(float)

    attributes = reps.rename(
        columns={"segment": "rep_segment", "region": "rep_region"}
    )[REP_ATTRIBUTES]
    joined = deals.merge(attributes, on="rep_id", how="left")
    return joined, unknown


def load_data(
    data_dir: Path | None = None,
    as_of: date | None = None,
) -> Data:
    """Read both snapshots and the quota source, normalized and joined."""
    as_of = as_of or config.AS_OF
    if data_dir is None:
        quota_source = config.QUOTA_SOURCE
        snapshot_paths = dict(config.SNAPSHOT_DIRS)
    else:
        quota_source = data_dir / "Q2" / "reps.csv"
        snapshot_paths = {name: data_dir / name / "deals.csv" for name in ("Q1", "Q2")}

    reps = _read_reps(quota_source)
    quotas = melt_quotas(reps)

    snapshots: dict[str, pd.DataFrame] = {}
    unknown: set[str] = set()
    for name, path in snapshot_paths.items():
        frame, unknown_here = _load_snapshot(path, reps)
        snapshots[name] = frame
        unknown |= unknown_here

    return Data(
        snapshots=snapshots,
        quotas=quotas,
        reps=reps,
        unknown_stages=tuple(sorted(unknown)),
        as_of=as_of,
    )


def quota_total(quotas: pd.DataFrame, period: str) -> float:
    return float(quotas.loc[quotas["period"] == period, "quota"].sum())


__all__ = [
    "CLOSED_LOST",
    "CLOSED_STAGES",
    "CLOSED_WON",
    "Data",
    "KNOWN_STAGES",
    "PERIODS",
    "load_data",
    "melt_quotas",
    "normalize_stage",
    "quota_total",
]
