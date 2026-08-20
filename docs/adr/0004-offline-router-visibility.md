# Offline router fallback is visibly flagged and may refuse

`router.py` falls back to a keyword-based matcher when the Sonnet call is
unavailable, so a network failure during a live demo degrades instead of
crashing. A keyword router misroutes more often than the LLM router, and
misroute is the one failure category the verifier cannot catch — a wrong
`Result`, computed correctly, still looks verified.

Decided the offline path must render a distinct UI banner and must still
populate `intent.restated`, templated from the intent it built, so a human
can catch a misroute from the restatement alone without opening the trace
panel. The offline router is also allowed to return `unsupported` rather than
guess when keyword matching is ambiguous — refusing is cheap, a wrong route
is expensive.
