"""Run the eval cases against the real models.

    python -m evals.run                 every case once
    python -m evals.run --repeat 3      each case three times, to see flakiness
    python -m evals.run --only loss     cases whose id contains "loss"

Every case goes through `ask`, the same seam the app uses, with a client
that records each model call and its token counts. Results print as a table
and save to evals/results/<timestamp>.json, and each run lists the cases
whose outcome changed since the newest earlier result.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from acme.loading import Data, load_data
from acme.pipeline import ask
from acme.query_log import QueryLog

from .cases import CASES, Case, Observed

RESULTS_DIR = Path(__file__).resolve().parent / "results"
NARRATE = "narrate"


class RecordingClient:
    """Wraps a model client and records every call's tool name and tokens.
    Duck-typed the same way the app's client is, so `ask` can't tell."""

    def __init__(self, inner: object):
        self._inner = inner
        self.calls: list[tuple[str, int, int]] = []
        self.messages = self

    def create(self, **kwargs):
        tools = kwargs.get("tools")
        name = tools[0]["name"] if tools else NARRATE
        try:
            response = self._inner.messages.create(**kwargs)
        except Exception:
            self.calls.append((name, 0, 0))
            raise
        usage = getattr(response, "usage", None)
        self.calls.append(
            (name, getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)
        )
        return response


@dataclass(frozen=True)
class CaseResult:
    id: str
    run: int
    passed: bool
    lane: str
    failures: tuple[str, ...]
    seconds: float
    calls: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    # "narrator" when model prose published, "blocked" when the verifier or
    # an API failure put the template up instead, None for a refusal.
    narration: str | None
    plan: dict | None
    text: str
    # The router's reading, for seeing why a question landed where it did.
    intent: dict | None
    # The narrator's blocked draft and its figures that matched no fact.
    blocked_draft: str
    unmatched: tuple[str, ...]


def _lane(answer) -> str:
    return "refused" if answer.kind == "refused" else answer.lane


def run_case(case: Case, run: int, data: Data, client: object, log_dir: Path) -> CaseResult:
    recorder = RecordingClient(client)
    log = QueryLog(log_dir / f"{case.id}-{run}.jsonl")
    started = time.perf_counter()
    answer = ask(case.question, data, recorder, log=log)
    seconds = time.perf_counter() - started

    records = log.records()
    plan = records[-1].plan if records else None
    lane = _lane(answer)
    failures: list[str] = []
    if answer.router_mode == "offline":
        failures.append("the router fell back to offline, so a model call failed")
    if lane != case.expect:
        failures.append(f"landed in {lane}, expected {case.expect}")
    else:
        observed = Observed(answer=answer, plan=plan, tools_called=tuple(c[0] for c in recorder.calls))
        for check in case.checks:
            failures.extend(check(observed, data))

    if answer.kind == "refused":
        narration, text, draft, unmatched = None, answer.reason, "", ()
    else:
        narration = "narrator" if answer.prose_source == "narrator" else "blocked" if answer.narrator_blocked else "template"
        text, draft, unmatched = answer.prose, answer.blocked_draft, answer.unmatched_figures

    return CaseResult(
        id=case.id,
        run=run,
        passed=not failures,
        lane=lane,
        failures=tuple(failures),
        seconds=round(seconds, 2),
        calls=tuple(c[0] for c in recorder.calls),
        input_tokens=sum(c[1] for c in recorder.calls),
        output_tokens=sum(c[2] for c in recorder.calls),
        narration=narration,
        plan=plan,
        text=text,
        intent=None if answer.intent is None else answer.intent.model_dump(exclude_none=True),
        blocked_draft=draft,
        unmatched=tuple(unmatched),
    )


def run_all(
    cases: tuple[Case, ...], data: Data, client: object, *, repeat: int = 1, workers: int = 4
) -> list[CaseResult]:
    jobs = [(case, run) for case in cases for run in range(1, repeat + 1)]
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_case, case, run, data, client, Path(tmp)) for case, run in jobs]
        results = [future.result() for future in futures]
    order = {case.id: i for i, case in enumerate(cases)}
    return sorted(results, key=lambda r: (order[r.id], r.run))


def pass_rates(results: list[CaseResult]) -> dict[str, float]:
    totals: dict[str, list[int]] = {}
    for result in results:
        passed, runs = totals.setdefault(result.id, [0, 0])
        totals[result.id] = [passed + result.passed, runs + 1]
    return {case_id: passed / runs for case_id, (passed, runs) in totals.items()}


def changes(previous: dict[str, float], current: dict[str, float]) -> list[str]:
    """One line per case whose pass rate moved, or that is new or gone."""
    lines = []
    for case_id in current:
        if case_id not in previous:
            lines.append(f"new       {case_id}: {current[case_id]:.0%}")
        elif previous[case_id] != current[case_id]:
            word = "improved" if current[case_id] > previous[case_id] else "regressed"
            lines.append(f"{word:<9} {case_id}: {previous[case_id]:.0%} -> {current[case_id]:.0%}")
    for case_id in previous:
        if case_id not in current:
            lines.append(f"gone      {case_id}")
    return lines


def report(results: list[CaseResult], cases: tuple[Case, ...], out: TextIO) -> None:
    expect = {case.id: case.expect for case in cases}
    notes = {case.id: case.note for case in cases}
    repeated = any(r.run > 1 for r in results)
    width = max(len(r.id) for r in results) + (4 if repeated else 0)
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        label = f"{result.id} #{result.run}" if repeated else result.id
        print(
            f"{mark}  {label:<{width}}  {result.lane:<12} {result.seconds:>5.1f}s  "
            f"{len(result.calls)} calls",
            file=out,
        )
        for failure in result.failures:
            print(f"        {failure}", file=out)
        if result.unmatched:
            figures = ", ".join(result.unmatched)
            print(f"        narrator blocked on {figures}: {result.blocked_draft[:160]}", file=out)
        if not result.passed and notes[result.id]:
            print(f"        note: {notes[result.id]}", file=out)

    print(file=out)
    for kind in ("metric", "exploratory", "refused"):
        scoped = [r for r in results if expect[r.id] == kind]
        if scoped:
            print(f"{kind:<12} {sum(r.passed for r in scoped)}/{len(scoped)} passed", file=out)
    answered = [r for r in results if r.narration is not None]
    blocked = [r for r in answered if r.narration != "narrator"]
    print(f"{'overall':<12} {sum(r.passed for r in results)}/{len(results)} passed", file=out)
    print(f"narration    {len(blocked)} of {len(answered)} answers fell back to the template", file=out)
    tokens_in = sum(r.input_tokens for r in results)
    tokens_out = sum(r.output_tokens for r in results)
    print(f"tokens       {tokens_in:,} in, {tokens_out:,} out", file=out)


def _latest(results_dir: Path) -> dict[str, float] | None:
    files = sorted(results_dir.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))["pass_rates"]


def main(
    argv: list[str] | None = None,
    *,
    out: TextIO = sys.stdout,
    client_factory: Callable[[], object] | None = None,
    results_dir: Path = RESULTS_DIR,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--only", default="")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    cases = tuple(case for case in CASES if args.only in case.id)
    if not cases:
        print(f"No case id contains {args.only!r}.", file=out)
        return 1

    if client_factory is None:
        import anthropic

        client_factory = anthropic.Anthropic
    data = load_data()
    started = time.perf_counter()
    results = run_all(cases, data, client_factory(), repeat=args.repeat, workers=args.workers)
    elapsed = time.perf_counter() - started

    report(results, cases, out)
    print(f"wall time    {elapsed:.0f}s", file=out)

    rates = pass_rates(results)
    previous = _latest(results_dir)
    if previous is not None and args.only:
        # A partial run only says something about the cases it ran.
        previous = {case_id: rate for case_id, rate in previous.items() if case_id in rates}
    if previous is not None:
        moved = changes(previous, rates)
        print(file=out)
        print("Since the last run:" if moved else "No change since the last run.", file=out)
        for line in moved:
            print(f"  {line}", file=out)

    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    path.write_text(
        json.dumps(
            {
                "args": vars(args),
                "pass_rates": rates,
                "results": [asdict(r) for r in results],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {path}", file=out)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
