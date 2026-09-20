# 0003. Authorization is bound to the action and revalidated at execution

Status: Accepted (Sprint 1, review rounds 1 and 2)

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

A second review round found that binding the action kind alone was not enough.
An operation carries `compensates`, naming the earlier write it undoes, and that
field appeared in neither the approved scope nor any fingerprint. Replacing it
on a confirmed operation still passed every check, so a confirmation to undo one
write also authorized undoing a different one.

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
value naming one plan item, the external action approved for it, and that
action's target. An approval's scope is a set of `ApprovedAction`, and the
payload fingerprint covers the item content, the action, and the target, so a
create confirmation cannot authorize a cancel and a confirmation to undo one
write cannot authorize undoing another.

`fingerprint_action` is the canonical description of a single external write.
An operation derives its idempotency key from it at proposal time, and
`authorize_operation` recomputes it from the operation's own fields. Substituting
any part of the approved action is therefore caught twice: once because the
reconstructed action is absent from the approved scope, and once because the
recomputed key no longer matches the stored one.

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
one approval, or as separate approvals. There is no wildcard action and no
wildcard target: an approval to cancel must name the write it undoes, which is
why an untargeted cancellation approval no longer authorizes a targeted one.

Retrying the identical authorized operation is unaffected, because neither the
action nor its target changes across attempts and the idempotency key stays
stable. This was a stated requirement of the review and is covered by a test.

`compensates` is currently the only modeled external target. When a future
adapter introduces others, such as the provider resource an update writes to,
they belong in `ApprovedAction` and in `_action_payload` for the same reason.

These are domain-level guarantees. Enforcing them across process restarts and
concurrent workers is Sprint 2 work and is not established by this record.
