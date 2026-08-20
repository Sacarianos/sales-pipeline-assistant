"""Configuration constants for the Acme pipeline assistant."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def _load_dotenv(path: Path) -> None:
    """Populate `os.environ` from a `KEY=VALUE` file, without overriding what's
    already set. No `python-dotenv` dependency for a two-line file."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(REPO_ROOT / ".env")

# The as-of date is pinned. It is never derived from the current date, so the
# same question gives the same answer whenever the demo runs.
AS_OF = date(2026, 5, 2)

# `data/Q2/reps.csv` is the quota source for both quarters. Its `quota_q1_2026`
# column is byte-identical to the same column in `data/Q1/reps.csv`, and the Q1
# file has no `quota_q2_2026` column at all.
QUOTA_SOURCE = DATA_DIR / "Q2" / "reps.csv"

SNAPSHOT_DIRS = {
    "Q1": DATA_DIR / "Q1" / "deals.csv",
    "Q2": DATA_DIR / "Q2" / "deals.csv",
}

# Model IDs live here even though issue 01 calls neither of them.
ROUTER_MODEL = "claude-sonnet-5"
NARRATOR_MODEL = "claude-haiku-4-5-20251001"
