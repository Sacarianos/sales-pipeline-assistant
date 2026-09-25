"""An append-only record of every exploratory attempt.

V3 promotes a plan that keeps recurring into a registered metric, and a
promote path built on a lane that never recorded anything starts with no
history. So every attempt the fallback lane makes appends one line here,
refusals included. A question the generator declined, or a plan the checker
rejected, says more about what the registry is missing than an answer does.

One JSON object per line, in a local file. Lines are only ever appended,
never rewritten, and nothing here sends question text anywhere.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# answered: the plan ran and published.
# declined: the generator said the frames can't answer it.
# rejected: the plan was malformed or failed the checker, so nothing ran.
# failed: the plan passed the checker and raised while running.
# unavailable: the generator call itself failed.
Outcome = Literal["answered", "declined", "rejected", "failed", "unavailable"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LogRecord:
    question: str
    outcome: Outcome
    # The plan exactly as the generator wrote it, before any parsing, so a
    # malformed plan is still on record. None for a decline.
    plan: dict | None = None
    reason: str | None = None
    # Rows the plan's filters matched, and rows in a tabular result. A
    # single-number answer has no row count.
    matched_rows: int | None = None
    row_count: int | None = None
    # True when the question followed on from an earlier one, like "just for
    # Enterprise". It still counts toward promotion but isn't an example.
    follows_up: bool = False
    logged_at: str = field(default_factory=_now)


class QueryLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: LogRecord) -> None:
        line = json.dumps(asdict(record), ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def records(self) -> list[LogRecord]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [LogRecord(**json.loads(line)) for line in handle if line.strip()]


__all__ = ["LogRecord", "Outcome", "QueryLog"]
