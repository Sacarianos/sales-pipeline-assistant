# 04: Query log

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** An append-only record of every fallback attempt, carrying
the question, the generated expression, whether validation passed, whether
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

**Status:** ready-for-agent

- [ ] Every fallback attempt appends exactly one record
- [ ] A record carries the question, the expression, validation outcome,
      execution outcome, and row count
- [ ] A generator decline is logged with its reason and no expression
- [ ] A validation rejection is logged with the expression that was rejected
- [ ] Metric-lane answers append nothing
- [ ] The log is append-only and never rewritten in place
- [ ] The log survives a restart
- [ ] No question text is sent anywhere off the machine
