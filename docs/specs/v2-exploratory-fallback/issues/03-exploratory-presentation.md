# 03: Exploratory presentation

**Parent:** [V2 exploratory fallback lane](../../v2-exploratory-fallback.md)

**What to build:** An exploratory answer that nobody could mistake for a
defined metric, without making it look broken.

The distinction being drawn is narrow and worth stating precisely on screen.
The numbers in an exploratory answer are computed by pandas and checked by the
verifier exactly as a metric's are. What is not pinned is whether the query
answered the question that was asked, because a model wrote it. So the
treatment marks the interpretation as unverified, not the arithmetic.

The generated expression renders expanded and never behind a click. It is the
one thing a reader cannot otherwise check, which makes it the thing that
belongs most in front of them.

The badge differs from the metric lane's. A verified metric answer says how
many figures were checked against computed values. An exploratory answer says
the figures were computed and checked but the query was model-written.

The four detail sections stay as they are. Flags still run, because a partial
period and a stale close date are properties of the data rather than of the
lane that read it.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] An exploratory answer is visually distinct from a metric answer
- [ ] The generated expression renders expanded, not behind a click
- [ ] An exploratory answer carries no verified-metric badge
- [ ] The badge says the figures were checked and the query was model-written
- [ ] The row count and the frame that was read are both shown
- [ ] Flags still run and render on an exploratory answer
- [ ] The four detail sections render as they do for a metric answer
- [ ] A truncated result says so and reports the full row count
