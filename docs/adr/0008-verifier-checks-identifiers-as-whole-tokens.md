# The verifier checks an identifier as one token, against the text the narrator was given

Refines ADR-0003. That rule stays: no token is exempt, and every number the
narrator may write reaches it as a fact.

The first eval run against the real models found every answer that named a
deal falling back to the template. The verifier read "OPP-079" as the
figure 79, which no fact held. Period labels had the same problem in the
exploratory lane: "Q2-2026" read as the figure 2026, and only the metric
lane supplies the year as a fact.

Adding every deal number as a fact would have been ADR-0003's approach, but
a deal ID's digits aren't a quantity, and a fact for each one would let "79"
verify anywhere in the prose. Skipping identifiers outright would fix the
false blocks and open a worse hole: the narrator could name a deal that
doesn't exist, and nothing would catch it.

Decided that a run of letters, a hyphen, and digits, like `OPP-079` or
`Q2-2026`, is one identifier token. It verifies only when it appears
verbatim in a fact's label or in the restatement the narrator was shown. Its
digits are never read as a figure, and it doesn't count toward the "N
figures verified" badge, since a label isn't a figure. Anything that isn't an
identifier is checked exactly as before, and a date like 2026-05-30, which
has no letters, still has to match facts digit group by digit group.
