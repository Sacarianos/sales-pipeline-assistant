"""Command line for promoting a recurring exploratory plan to a metric.

    python -m acme.promote list
    python -m acme.promote promote <id> --name loss_reasons \\
        --description "..." --grouping segment

`list` shows the candidates in the query log, most asked first. `promote`
writes a metric file under `acme/metrics/` once every decision the V3
spec asks for has been made, and otherwise lists what's missing and writes
nothing. Restart the app afterwards to load the new metric.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from . import config
from .loading import load_data
from .promoted import PERIOD_FRAMES
from .promotion import Promotion, PromotionRefused, find_candidates, promote
from .query_log import QueryLog

METRICS_DIR = Path(__file__).resolve().parent / "metrics"
MAX_SUGGESTED_EXAMPLES = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m acme.promote")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="show candidates from the query log")
    listing.add_argument("--log", type=Path, default=config.QUERY_LOG_PATH)

    promoting = commands.add_parser("promote", help="write a metric from a candidate")
    promoting.add_argument("candidate")
    promoting.add_argument("--log", type=Path, default=config.QUERY_LOG_PATH)
    promoting.add_argument("--metrics-dir", type=Path, default=METRICS_DIR)
    promoting.add_argument("--name", required=True)
    promoting.add_argument("--description", required=True, help="the definition, in your own words")
    promoting.add_argument("--grouping", action="append", default=[], help="segment, rep, or manager; repeatable")
    promoting.add_argument("--example", action="append", default=[], help="an example question; repeatable")
    promoting.add_argument(
        "--definition", action="append", default=None,
        help="a definition key the answer rests on; repeatable",
    )
    return parser


def _list(candidates, out: TextIO) -> int:
    if not candidates:
        print("No candidates yet. The query log has no answered exploratory plans.", file=out)
        return 0
    for c in candidates:
        print(f"{c.id}  asked {c.count} time{'s' if c.count != 1 else ''}", file=out)
        print(f"  For the current period it reads: {c.description}", file=out)
        if c.scope_seen:
            seen = "; ".join(f"{field} {', '.join(values)}" for field, values in c.scope_seen.items())
            print(f"  Asked scoped to: {seen}", file=out)
        for question in c.questions:
            print(f'  - "{question}"', file=out)
        print(file=out)
    return 0


def _promote(args, candidates, data, out: TextIO) -> int:
    candidate = next((c for c in candidates if c.id == args.candidate), None)
    if candidate is None:
        print(f"There's no candidate '{args.candidate}'. Run `list` to see them.", file=out)
        return 1

    reads_periods = candidate.plan["frame"] in PERIOD_FRAMES
    definition_keys = args.definition if args.definition is not None else (
        ["period_membership"] if reads_periods else []
    )
    promotion = Promotion(
        name=args.name,
        description=args.description,
        groupings=tuple(args.grouping),
        examples=tuple(args.example) or candidate.questions[:MAX_SUGGESTED_EXAMPLES],
        definition_keys=tuple(definition_keys),
    )
    try:
        path = promote(promotion, candidate, data, args.metrics_dir)
    except PromotionRefused as refused:
        print("Nothing written. Still to decide:", file=out)
        for problem in refused.problems:
            print(f"  - {problem}", file=out)
        return 1

    print(f"Wrote {path}", file=out)
    if reads_periods:
        print(
            "  The logged plan read a whole snapshot. The metric reads only the "
            "period each question asks about.",
            file=out,
        )
    groupings = ", ".join(("overall", *promotion.groupings))
    print(f"  Answers at: {groupings}", file=out)
    print(f"  Examples: {'; '.join(promotion.examples)}", file=out)
    print("Restart the app to load it.", file=out)
    return 0


def main(argv: list[str] | None = None, *, out: TextIO = sys.stdout) -> int:
    args = _parser().parse_args(argv)
    data = load_data()
    candidates = find_candidates(QueryLog(args.log).records(), data)
    if args.command == "list":
        return _list(candidates, out)
    return _promote(args, candidates, data, out)


if __name__ == "__main__":
    sys.exit(main())
