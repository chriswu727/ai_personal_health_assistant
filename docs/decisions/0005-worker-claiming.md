# 0005. Worker claiming, and the one access path that is not owner-scoped

Status: Accepted (Sprint 2, task S2-05)

## Context

A worker takes operations from the queue and executes them. Two workers must
never hold the same operation, a worker that dies must not strand its work, and
authorization must still be checked at the moment of execution rather than
trusted from when the operation was queued.

This sits awkwardly against the rule that every repository access path is scoped
to an owner. A worker serves every user's queue, so its scan cannot name one
owner in advance.

## Alternatives

- **A dedicated queue broker.** Correct and well understood, but it puts the
  queue outside the database, so enqueueing an operation and committing the row
  that describes it stop being one transaction. The architecture already says to
  start with a database-backed mechanism and introduce a broker once contention
  is measured.
- **A status flag updated optimistically**, with each worker writing `claimed`
  and retrying on conflict. Works, but under contention every worker but one
  does wasted work, and the retry loop becomes the thing to tune.
- **PostgreSQL advisory locks.** Avoids row locks, but the lock is then keyed by
  something derived rather than by the row itself, and a mistake in that
  derivation is invisible.
- **Scanning per user**, iterating owners so the query stays owner-scoped. This
  keeps the rule intact in letter and breaks it in spirit: the iteration is
  still cross-user, and it adds a query per user with no work in it.
- **Re-checking authorization inside the claim query.** Fast, but it would be a
  second implementation of the authorization rules in SQL, next to the one in
  the domain, free to drift from it.

## Decision

Claiming uses `SELECT ... FOR UPDATE SKIP LOCKED` on the operations table, taking
the oldest queued row that no other transaction holds. A second worker skips a
locked row rather than waiting behind it, and the lock lasts exactly as long as
the surrounding transaction.

`claim_next` is the single access path that is not owner-scoped, and it is named
and documented so that it stays findable. It returns an operation to work on and
no user content. Everything the worker loads next, the plan and the approval, is
fetched with that operation's own owner, so authorization stays owner-scoped even
though the scan is not.

Whether a row may execute is the domain's decision, not the query's. The
application layer loads the plan and approval and calls the same
`authorize_operation` path the confirmation flow uses. An operation whose
authorization has lapsed is cancelled with the reason recorded, rather than left
in the queue: nothing about waiting makes an expired confirmation valid again,
and leaving it would spin.

An expired lease is released to `outcome_unknown`, never to `failed`. The
external write may have landed, and only reconciliation against the provider can
say.

## Consequences

The queue stays inside the database, so an operation and its queue entry commit
or roll back together. The cost is that queue throughput is now database
throughput; a broker becomes justified when contention is measured, not before,
and that measurement belongs to Sprint 7.

`SKIP LOCKED` makes claiming lock-free between workers but says nothing about
fairness: a row a worker holds for a long time simply waits. Long-running
executions are bounded by the lease rather than by the claim.

A user can now see an operation they confirmed end as cancelled without any
external attempt, because their confirmation expired first. That is the intended
behavior and the interface must explain it rather than hide it, which is work
for the delivery layer.

The non-owner-scoped path is a standing exception. If a second one appears, that
is the moment to reconsider whether ownership belongs in the repository layer at
all, rather than quietly accumulating exceptions to a rule.
