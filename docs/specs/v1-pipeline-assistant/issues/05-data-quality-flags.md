# 05: Data-quality flags

**Parent:** [V1 Acme pipeline assistant](../../v1-pipeline-assistant.md)

**What to build:** A sales leader is told, without asking, when the data behind
an answer has a problem worth knowing about. Stale forecast dates, missing
values, and stage names the system doesn't recognize all surface in the flags
panel next to the answer they affect.

Each rule is a function taking a result, an intent, and context, returning a flag
or nothing. All rules run and all results are collected, because the list itself
is displayed rather than being buried as conditionals inside metric code.

Stale close date catches open deals whose forecast close has already passed as of
2026-05-02. Two deals in the Q2 snapshot qualify. A leader forecasting on
pipeline that was supposed to have closed already should know that before they
commit to a number.

Missing field catches nulls in a field the answer depends on. One of the nine
closed-lost deals has no loss reason.

Unknown stage is the loud half of the open-as-complement decision. An
unrecognized stage still counts as open, and the flag says the system met a name
it hadn't been told about. The alternative is a whitelist that silently shrinks a
number when the vocabulary changes, which is how a wrong figure reaches a screen
with nothing to warn anyone.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Open deals with a close date at or before the as-of date raise the stale
      flag, naming the deals
- [ ] Two deals qualify as stale in the Q2 snapshot
- [ ] Nulls in a field the answer depends on raise the missing-field flag
- [ ] The single closed-lost deal with no loss reason is caught by that rule
- [ ] A stage name absent from the known-stage registry raises the unknown-stage
      flag and the deal still counts as open
- [ ] Every rule runs on every answer and all resulting flags are collected, with
      no rule short-circuiting another
- [ ] Flags render in the panel without any click
