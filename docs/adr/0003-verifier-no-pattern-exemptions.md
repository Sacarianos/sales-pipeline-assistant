# Verifier exempts no numeric token by pattern; every number the narrator may write is a Fact

Prose legitimately contains numbers that aren't computed claims — "Q2 2026,"
"day 32 of 91." Exempting those by regex (skip 4-digit years, skip ordinals)
gives the verifier's guarantee silent carve-outs, which is a harder thing to
defend to a skeptical executive than "every number is checked, no
exceptions."

Decided to put those values into `facts` as well (`period_year`,
`day_of_quarter`, `days_in_quarter`, etc.) instead of exempting them. The
verifier's rule stays absolute: any numeric token without a matching fact
discards the prose and falls back to `result.template`.
