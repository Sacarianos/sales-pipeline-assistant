# 04: Query log

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** An append-only record of every fallback attempt, carrying
the question, the generated query plan, whether validation passed, whether
execution succeeded, and the row count.

This ships in V2 rather than with V3 because V3 promotes a query that keeps
recurring, and a promote path built on top of a lane that has been answering
questions without recording them starts with no history to promote from. The
log is the cheapest possible thing that makes V3 possible.

Refusals are logged too. A question the generator declined and a query the
validator rejected are both worth more than a successful one when the time
comes to work out what the registry is missing, and a log that only records
successes describes a system nobody actually used.

Append-only and local. No question text leaves the machine.

**Blocked by:** 02

**Status:** ready-for-human

- [x] Every fallback attempt appends exactly one record
- [x] A record carries the question, the plan, validation outcome,
      execution outcome, and row count
- [x] A generator decline is logged with its reason and no plan
- [x] A validation rejection is logged with the plan that was rejected and the reason
- [x] Metric-lane answers append nothing
- [x] The log is append-only and never rewritten in place
- [x] The log survives a restart
- [x] No question text is sent anywhere off the machine

## Notes

Built in `acme/query_log.py`: one JSON object per line in
`logs/query_log.jsonl`, which git ignores because it holds the questions
people asked. `ask` takes the log as an optional argument and hands it to the
fallback lane, and the app passes one cached instance. Tests point it at a
temporary file.

Validation and execution outcomes fold into one `outcome` field, since
they're never independent. `answered` means the plan ran. `declined` means
the generator said the frames can't answer it. `rejected` means the plan was
malformed or failed the checker, so nothing ran. `failed` means it passed the
checker and raised while running. `unavailable` means the generator call
itself failed, which the spec didn't cover but is still an attempt.

The plan is stored exactly as the generator wrote it, before parsing, so a
malformed plan is on record too. No client means no attempt, so nothing is
logged in offline mode.

Checked end to end in the running app with a scripted client: an answered,
a rejected, and a declined question each appended one line with the right
outcome. 202 passing.
