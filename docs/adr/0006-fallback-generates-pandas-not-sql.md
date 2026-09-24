# The exploratory fallback generates pandas validated as an AST, not SQL validated by sqlglot

Superseded in part by ADR-0007. The lane still reads the loader's frames
instead of the CSVs, for the reasons below. The AST sandbox did not hold up:
the generator now fills a structured query plan and no model-written code
runs.

V1's further notes planned a text-to-SQL lane over DuckDB, with `sqlglot`
proving each generated statement was a single read-only select against
whitelisted tables before it ran.

The problem is that the numbers this system trusts do not live in the CSVs.
They live in the frames the loader builds. Period membership, `is_open` as the
complement of the two closed stages, the rep attributes joined onto every deal,
the melted one-row-per-rep-per-period quota table: all of that is applied at
load time and none of it exists in the raw files. A SQL lane over DuckDB would
have to either reimplement those rules in SQL or export the frames and keep two
definitions in step. A fallback that disagrees with the metric lane about what
"open" means is worse than having no fallback, because both answers look
equally confident and only one of them is right.

Generating pandas against the frames the metrics already use removes that
entire class of divergence. It also drops two dependencies that would have
existed for one lane.

The cost is real: `sqlglot` was providing a static guarantee, and pandas is
Python, so "just run what the model wrote" is arbitrary code execution.

Decided to generate a single pandas expression and replace the sqlglot
guarantee with an equivalent one built on Python's own `ast` module. The
expression is parsed with `ast.parse(mode="eval")` and every node is walked
against an allowlist before anything executes: only named frames may be
referenced, only allowlisted methods may be called, and attribute access to
any name beginning with an underscore is rejected outright, along with
imports, lambdas, comprehensions, assignments, and calls to anything not on
the list. Execution happens with `__builtins__` emptied and only the
allowlisted frames in scope.

Validation runs before execution and a rejected expression is a refusal, never
a repair or a retry with the offending part removed. This keeps the property
that made sqlglot worth having: whether the generated query is safe to run is
decided by reading it, not by running it and hoping.
