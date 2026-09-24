# The exploratory fallback runs a structured query plan, not generated pandas

Supersedes the sandbox half of ADR-0006. The other half stands: the lane
still reads the frames the loader builds, never the raw CSVs, so it can't
disagree with the metrics about what "open" means.

ADR-0006 had the generator write a pandas expression, walked it as an AST
against an allowlist, and ran it with builtins emptied. The ADR's claim was
that whether a query is safe to run is decided by reading it. That turned
out false in two ways, both reproduced end to end through `ask`.

`agg` was on the method allowlist, and pandas resolves a string passed to
`agg` to any method on the frame. `deals_q2.agg("to_csv", path_or_buf=...)`
passed validation and wrote a file, and the reader saw a refusal while the
write had already happened. The allowlist checked attribute names in the tree
and never looked inside string arguments, and pandas has more of these
string-dispatch paths than an allowlist can reasonably track.

`9 ** 9 ** 9` also passed, since power and integer constants were allowed,
and it hung the process. Nothing bounded CPU or memory.

Both are patchable one at a time. The pattern isn't. An allowlist over a
general-purpose library's call surface has to know every way that surface
reaches back into itself.

A third problem had nothing to do with safety. User story 3 promises the
sales leader the one thing they can't otherwise check, and the lane handed
them `deals_q2[deals_q2['stage'] == 'Closed Lost'].groupby(...)`. A CCO can't
read that.

Decided to have the generator fill a structured query plan through a forced
tool, the same pattern the router uses for `Intent`. A plan names one frame,
a list of filters, up to two group-by columns, one aggregate from a fixed
set, a sort key, and a row limit, or it declines with a reason. Code in
`acme/query_plan.py` checks the plan against the frame schemas and runs
it with pandas written by hand. Nothing the model writes is evaluated. A
filter value is data compared against a column, so a string holding code
matches no rows.

What that buys:

- The sandbox is gone, and so is the class of bug it had. There is no string
  the model can write that executes.
- The plan converts to a plain English sentence with no model involved, and
  that sentence is what the reader sees first. The equivalent pandas is
  still shown under it for an analyst, and tests pin that code to the result
  that actually ran.
- One frame per plan makes blending the two snapshots structurally
  impossible. The whole-tree mutual exclusion check is no longer needed.
- Refused topics are enforced in this lane too. The region columns are
  withheld from every plan, so "which territory has the most pipeline",
  which never says "region" and used to reach the deal-side region column
  through the old lane, is rejected before anything runs.
- A category filter must name a value the column actually holds. A typo like
  `Closed-Lost` refuses instead of silently matching zero rows.
- V3's promote-to-metric path gets simpler, since a plan that keeps
  recurring in the query log is already close to a metric definition.

The cost is expressiveness. A plan can't chain operations, join frames, or
do arithmetic between columns. For the questions this lane exists for, like
loss reasons, stage breakdowns, top accounts, and deal listings, filter,
group, and aggregate covers them. A question that needs more is declined,
which is the failure mode the spec already asks for, and a declined question
is exactly what the query log is there to collect.
