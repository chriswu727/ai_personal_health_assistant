# 0003. Authorization is bound to the action and revalidated at execution

Status: Accepted (Sprint 1, review round 1)

## Context

Review of pull request #1 reproduced four defects in the consent boundary, all
in code that had a passing test suite:

1. `retry()` authorized its transition from the shared transition table, which
   also permits `awaiting_confirmation -> queued` for `confirm()`. Calling
   `retry()` on an unconfirmed operation queued it without any approval check,
   and it then executed with `approval_id=None`.
2. `confirm()` compared the operation's plan version against the supplied plan
   but never its owner or plan identifier. Two users' plans can both be at
   version 1 and both contain an item called `item-a`, so one user's approval
   could queue another user's operation.
3. The approval fingerprint covered only item content. A confirmation to create
   a calendar event also authorized cancelling it, which contradicted the stated
   requirement that compensation be separately authorized.
4. `claim()` checked state, lease, and attempt budget but not authorization. A
   confirmation with a thirty-minute expiry could queue work that still entered
   execution well after it expired, and revocation after queuing was never seen.

The common cause: each function validated its own local preconditions, and the
tests did the same. Nothing checked that operation, plan, and approval described
one proposal, or that a transition's entry point matched its source state.

## Alternatives

- **Check the transition table more carefully at each call site.** Leaves the
  same class of defect available to the next function that targets a shared
  state.
- **Forbid all approval reuse by consuming an approval on first use.** Blocks
  the action-substitution attack, but also blocks legitimate retries of an
  already authorized action, which the recovery design requires.
- **Validate only at confirmation and treat queued work as authorized.** Simpler
  and faster, but it makes an expiry meaningless and leaves revocation unable to
  stop work already in the queue.

## Decision

`OperationKind` moves to `domain/actions.py` alongside a new `ApprovedAction`
value pairing one plan item with one external action. An approval's scope is a
set of `ApprovedAction`, and the payload fingerprint covers both the item
content and the action, so a create confirmation cannot authorize a cancel.

`_require_state` replaces bare transition-table checks wherever more than one
entry point can reach a state. Each function now names the single state it
starts from, and `retry()` accepts only a verified failure.

`authorize_operation` is a single helper used by both `confirm()` and `claim()`.
It compares owner, plan identifier, plan version, and the item content the
operation was derived from, then delegates to `authorize_execution` for the
approval's own checks. `claim()` additionally requires that the approval
presented is the one that queued the operation.

Authorization is therefore checked twice: when work is queued, and again at the
execution boundary before any external write.

## Consequences

`claim()` now requires the current approval and plan. A worker cannot dispatch
an operation from the queue row alone; it must load the authorizing context.
Sprint 2 persistence must make that load cheap and must keep the approval
reachable from the queued operation.

An expiry now means what it says: queued work whose confirmation expired will
not execute, and must be re-confirmed. This is deliberate. The alternative is a
queue backlog silently converting a short-lived consent into an open-ended one.

Mixed-action confirmations are expressed as multiple `ApprovedAction` entries in
one approval, or as separate approvals. There is no wildcard action.

These are domain-level guarantees. Enforcing them across process restarts and
concurrent workers is Sprint 2 work and is not established by this record.
