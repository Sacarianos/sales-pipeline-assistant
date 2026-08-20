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
    "best_case": (
        "Best case is closed-won revenue plus all open pipeline for the period, "
        "as if every open deal closes. It answers a different question than "
        "attainment does: not what has been won, but the most this period could "
        "possibly become, and it is never folded into the attainment percentage."
    ),
    "win_rate_weighted": (
        "Win-rate-weighted pipeline scales open pipeline by the period's win rate "
        "by value — closed-won revenue divided by all closed revenue, won and "
        "lost — rather than assuming every open deal closes. It is a second, more "
        "conservative estimate alongside best case, not a replacement for either "
        "attainment or best case."
    ),
    "restated": (
        "The restated figure recomputes a Q1 number from the Q2 snapshot, showing "
        "what those Q1 deals look like now that reopenings, unwinds, and ID reuse "
        "have come to light. As-reported is what the business committed to at the "
        "time; restated is what the current data supports. The two are never "
        "blended into one number."
    ),
    "best_case_coverage": (
        "Best-case coverage is best case — closed-won plus open pipeline — "
        "divided by quota, per rep. It answers whether a rep can still make "
        "quota this quarter if every open deal they have closes. Below 100 "
        "percent means they cannot, even in that best case."
    ),
}


def definition(key: str) -> str:
    return DEFINITIONS[key]


def title(key: str) -> str:
    return key.replace("_", " ").capitalize()
