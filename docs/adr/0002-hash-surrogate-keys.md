# 0002. Deterministic hash surrogate keys

**Status:** Accepted

## Context

A star schema usually assigns dimension surrogate keys from a sequence and resolves
them for each fact row with a lookup against the dimension. That makes the fact build
depend on the current state of every dimension, so one month cannot be rebuilt in
isolation, and two runs can assign different keys to the same member.

## Decision

`dim_date` keys on the integer `yyyymmdd`. The other dimensions key on
`xxhash64(dimension name, natural key)`. The fact build computes the same hash from the
trip's natural codes, so it needs no join to the dimensions. Every dimension has an
unknown member with code `-1`, and a null or unlisted code maps to it.

## Consequences

- Any month's facts can be rebuilt on its own, in any order, and produce identical keys.
- Referential integrity is not guaranteed by construction; the quality suite checks it
  for every foreign key, every month.
- A 64-bit hash can collide. With fewer than 300 members per dimension the probability is
  negligible, and a collision would surface as a duplicate key in the dimension, which
  the model tests check for.
- Keys are opaque and not ordered, so they cannot be used for range filters; queries
  filter on `pickup_date_key` or on dimension attributes instead.
