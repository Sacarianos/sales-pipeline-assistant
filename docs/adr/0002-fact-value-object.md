# Fact value object replaces a raw float dict as the narrator/verifier contract

The narrator needs labels, not just numbers — rep names in the risk answer,
the day-count in a partial-period disclosure. A bare `dict[str, float]` can't
carry that. Adding an unchecked parallel channel, such as a separate labels
dict the narrator also reads, would give the model a place to introduce a
number the verifier never checks, defeating the point of the contract.

Decided to make `Result.facts` a `dict[str, Fact]`, where `Fact` bundles
`value`, `unit` (currency / percent / count / date), and `label`. The
verifier still validates only `Fact.value`, so the no-unchecked-number
guarantee is unchanged, and `unit` lets both the verifier and the narrator
prompt reason about a value without guessing from its magnitude.
