"""Plain-English business definitions, kept out of the computation code.

A metric declares which keys it rests on; the flag layer turns each key into a
line the sales leader reads. The text lives here so that changing what the user
is told never means editing a pandas expression.
"""

from __future__ import annotations

DEFINITIONS: dict[str, str] = {
    "attainment": (
        "Attainment is closed-won revenue for the period divided by the quota for "
        "the period. Open pipeline is not counted, so a quarter with a large "
        "pipeline and nothing signed reads low."
    ),
    "period_membership": (
        "A deal counts toward the quarter its close date falls in, whether it is "
        "open or closed. No other date on the deal decides which quarter it "
        "belongs to."
    ),
    "open_deal": (
        "A deal is open when its stage is neither Closed Won nor Closed Lost. "
        "Open is worked out by exclusion, so a stage name nobody has seen before "
        "still counts as open instead of quietly disappearing."
    ),
    "quota_source": (
        "Quotas come from data/Q2/reps.csv for both quarters, one figure per rep "
        "per quarter."
    ),
}


def definition(key: str) -> str:
    return DEFINITIONS[key]


def title(key: str) -> str:
    return key.replace("_", " ").capitalize()
