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

`claim_next` and `expired_leases` are the two access paths that are not
owner-scoped, and they are named and documented so that they stay findable. Both
return operations to work on and no user content. Everything the worker loads
next, the plan and the approval, is fetched with that operation's own owner, so
authorization stays owner-scoped even though the scans are not.

Whether a row may execute is the domain's decision, not the query's. The
application layer loads the plan and approval and calls the same
`authorize_operation` path the confirmation flow uses. An operation whose
authorization has lapsed is cancelled with the reason recorded, rather than left
in the queue: nothing about waiting makes an expired confirmation valid again,
and leaving it would spin.

That check is only worth anything against current records, and three things make
it so:

- The plan is loaded at its **newest** version, not at the version the operation
  was queued under. A revision the user made while the work waited is exactly
  what should invalidate the confirmation, and reloading the queued version
  would compare it against itself.
- The plan row and the approval row are read for update. A revision or a
  revocation committing at the same moment then orders itself against the claim
  instead of slipping between the read and the commit. A new plan version is an
  insert, so the plan row rather than the version row is the point they order on.
- Advancing an operation is conditional on the snapshot the caller read: its
  state, attempt count, and update instant form the update's condition. A write
  built on a stale read is refused as a conflict rather than applied. `SKIP
  LOCKED` orders two simultaneous claims; it does nothing about a write that
  arrives later carrying an older view, which could otherwise erase a live lease
  or regress a settled outcome.

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

Insertion and advancement are separate operations, so a caller cannot create a
row by accident while meaning to advance one, and the conditional update has a
snapshot to compare against. Callers must keep the object they read, which is
the cost of not carrying a revision column into the domain.

Holding the plan row for the length of a claim means a revision briefly waits
behind a worker. Claims are short, and the alternative is a confirmation that
outlives the plan it described.

The non-owner-scoped paths are a standing exception, and there are two of them
rather than one. If a third appears, that is the moment to reconsider whether
ownership belongs in the repository layer at all, rather than quietly
accumulating exceptions to a rule.
