# Router defaults to the current period when a question doesn't name one

`Intent.period` is required, but a natural question like "how is Enterprise
tracking?" doesn't name a quarter. The router's philosophy elsewhere is
"guessing is worse than refusing," which argues for refusing an unstated
period the same way it refuses an unstated metric or segment. But `as_of` already
pins a single current moment, and forcing a quarter name onto every question
would make the tool more annoying than the reporting it replaces.

Decided to default to the period containing `as_of` (Q2-2026) when the
question doesn't name one, and to have `intent.restated` say so explicitly
("reading this as Q2-2026") so a wrong default is visible the same way a
wrong metric or segment guess would be. Refusal stays reserved for the cases
already committed to it: unknown metric, unknown segment/rep, region.
