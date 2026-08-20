# Detect ID reuse before classifying unwon or drifted deals

Diffing `Q1/deals.csv` against `Q2/deals.csv` shows 13 deal IDs where
`account_name` and `created_date` both change between snapshots — a different
deal has reused an earlier deal's identifier. A plain outer join on `deal_id`
reads 12 of those as `unwon`, misreporting 1,220,000 of revenue as reversed
when it was never won by that account in the first place.

Decided to detect ID reuse generically — both `account_name` and
`created_date` changed — rather than hardcode the 13 IDs, and to give it its
own `id_reused` change type that takes precedence over `unwon` and `drifted`
for that row. This keeps the reconciler correct against next quarter's
snapshot without maintaining an ID list by hand.
