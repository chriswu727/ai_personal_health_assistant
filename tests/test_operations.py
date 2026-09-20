"""External operation lifecycle: authorization, ambiguous outcomes, and leases."""

from dataclasses import dataclass, replace
from datetime import timedelta

import pytest

from health_assistant.domain.actions import ApprovedAction, OperationKind
from health_assistant.domain.approvals import Approval, grant_approval
from health_assistant.domain.errors import (
    ApprovalActionNotAuthorizedError,
    ApprovalExpiredError,
    ApprovalRevokedError,
    InvalidTransitionError,
    LeaseHeldError,
    LeaseNotHeldError,
    OperationIdentityError,
    OwnershipError,
    ReconciliationRequiredError,
    RetryBudgetExhaustedError,
    ValidationError,
)
from health_assistant.domain.identifiers import ApprovalId, OperationId, PlanId, PlanItemId
from health_assistant.domain.operations import (
    ALLOWED_TRANSITIONS,
    Lease,
    OperationState,
    ProviderOutcome,
    ToolOperation,
    cancel,
    claim,
    confirm,
    expire_lease,
    propose,
    reconcile,
    record_ambiguous_outcome,
    record_failure,
    record_success,
    request_confirmation,
    retry,
)
from health_assistant.domain.plans import CompletionStatus, PlanVersion
from tests.support import (
    EMPTY_CONSTRAINTS,
    OTHER_USER,
    OWNER,
    at,
    make_item,
    make_plan,
    make_scope,
)

TTL = timedelta(minutes=30)
LEASE = timedelta(minutes=5)
ITEM = PlanItemId("item-a")
SCOPE = make_scope("item-a")


@dataclass(frozen=True, slots=True)
class Queued:
    """A confirmed operation together with the plan and approval that queued it."""

    plan: PlanVersion
    approval: Approval
    operation: ToolOperation


def _plan() -> PlanVersion:
    return make_plan(make_item("item-a"), make_item("item-b", start_hours=48))


def _approval(
    plan: PlanVersion,
    *,
    approval_id: str = "approval-1",
    scope: frozenset[ApprovedAction] = SCOPE,
    ttl: timedelta = TTL,
) -> Approval:
    return grant_approval(
        approval_id=ApprovalId(approval_id),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=scope,
        actor_id=OWNER,
        now=at(),
        ttl=ttl,
    )


def _awaiting(
    plan: PlanVersion,
    *,
    kind: OperationKind = OperationKind.CREATE_EVENT,
    operation_id: str = "op-1",
) -> ToolOperation:
    return request_confirmation(
        propose(
            operation_id=OperationId(operation_id),
            plan=plan,
            item_id=ITEM,
            kind=kind,
            now=at(),
        ),
        now=at(minutes=1),
    )


def _queued(plan: PlanVersion | None = None) -> Queued:
    plan = plan if plan is not None else _plan()
    approval = _approval(plan)
    operation = confirm(
        _awaiting(plan), approval=approval, plan=plan, actor_id=OWNER, now=at(minutes=2)
    )
    return Queued(plan=plan, approval=approval, operation=operation)


def _execute(queued: Queued, *, worker_id: str = "worker-1", minutes: float = 3) -> ToolOperation:
    return claim(
        queued.operation,
        approval=queued.approval,
        plan=queued.plan,
        worker_id=worker_id,
        now=at(minutes=minutes),
        lease_duration=LEASE,
    )


def test_terminal_states_permit_no_further_transition() -> None:
    assert ALLOWED_TRANSITIONS[OperationState.SUCCEEDED] == frozenset()
    assert ALLOWED_TRANSITIONS[OperationState.CANCELLED] == frozenset()


def test_an_unknown_outcome_may_not_be_requeued_directly() -> None:
    assert OperationState.QUEUED not in ALLOWED_TRANSITIONS[OperationState.OUTCOME_UNKNOWN]


def test_a_reported_item_cannot_be_proposed_for_execution() -> None:
    plan = make_plan(make_item("item-a", completion=CompletionStatus.COMPLETED))
    with pytest.raises(ValidationError):
        propose(
            operation_id=OperationId("op-1"),
            plan=plan,
            item_id=ITEM,
            kind=OperationKind.CREATE_EVENT,
            now=at(),
        )


def test_confirmation_requires_an_unexpired_approval() -> None:
    plan = _plan()
    awaiting = _awaiting(plan)

    with pytest.raises(ApprovalExpiredError):
        confirm(
            awaiting,
            approval=_approval(plan),
            plan=plan,
            actor_id=OWNER,
            now=at(minutes=31),
        )
    assert awaiting.state is OperationState.AWAITING_CONFIRMATION


def test_only_the_owner_may_confirm_an_operation() -> None:
    plan = _plan()
    with pytest.raises(OwnershipError):
        confirm(
            _awaiting(plan),
            approval=_approval(plan),
            plan=plan,
            actor_id=OTHER_USER,
            now=at(minutes=2),
        )


def test_queueing_without_passing_through_confirmation_is_refused() -> None:
    plan = _plan()
    proposed = propose(
        operation_id=OperationId("op-1"),
        plan=plan,
        item_id=ITEM,
        kind=OperationKind.CREATE_EVENT,
        now=at(),
    )

    with pytest.raises(InvalidTransitionError):
        confirm(proposed, approval=_approval(plan), plan=plan, actor_id=OWNER, now=at(minutes=2))


def test_retry_cannot_queue_an_operation_that_was_never_confirmed() -> None:
    """Regression: the transition table alone also permits awaiting -> queued."""
    awaiting = _awaiting(_plan())

    with pytest.raises(InvalidTransitionError):
        retry(awaiting, now=at(minutes=2))


@pytest.mark.parametrize("state", [OperationState.PROPOSED, OperationState.QUEUED])
def test_retry_is_refused_from_any_state_but_a_verified_failure(
    state: OperationState,
) -> None:
    queued = _queued()
    operation = replace(queued.operation, state=state)

    with pytest.raises(InvalidTransitionError):
        retry(operation, now=at(minutes=5))


def _foreign_plan() -> PlanVersion:
    """Another user's plan that legitimately shares version 1 and item-a."""
    return PlanVersion.initial(
        plan_id=PlanId("other-plan"),
        owner_id=OTHER_USER,
        items=[make_item("item-a", title="Another user's activity")],
        created_at=at(),
    )


def test_an_operation_owner_cannot_confirm_with_another_users_approval() -> None:
    """Regression: two plans can share a version number and an item identifier."""
    approved = _plan()

    with pytest.raises(OperationIdentityError):
        confirm(
            _awaiting(_foreign_plan(), operation_id="op-foreign"),
            approval=_approval(approved),
            plan=approved,
            actor_id=OTHER_USER,
            now=at(minutes=2),
        )


def test_confirming_another_users_operation_is_refused_before_authorization() -> None:
    approved = _plan()

    with pytest.raises(OwnershipError):
        confirm(
            _awaiting(_foreign_plan(), operation_id="op-foreign"),
            approval=_approval(approved),
            plan=approved,
            actor_id=OWNER,
            now=at(minutes=2),
        )


def test_confirmation_is_refused_when_the_operation_names_a_different_plan() -> None:
    approved = _plan()
    other = PlanVersion.initial(
        plan_id=PlanId("second-plan"),
        owner_id=OWNER,
        items=[make_item("item-a")],
        created_at=at(),
    )

    with pytest.raises(OperationIdentityError):
        confirm(
            _awaiting(other, operation_id="op-second"),
            approval=_approval(approved),
            plan=approved,
            actor_id=OWNER,
            now=at(minutes=2),
        )


def test_a_create_approval_cannot_confirm_a_cancellation() -> None:
    """Regression: undoing a confirmed write needs its own authorization."""
    plan = _plan()

    with pytest.raises(ApprovalActionNotAuthorizedError):
        confirm(
            _awaiting(plan, kind=OperationKind.CANCEL_EVENT, operation_id="op-cancel"),
            approval=_approval(plan),
            plan=plan,
            actor_id=OWNER,
            now=at(minutes=2),
        )


def test_claiming_records_an_attempt_and_a_lease() -> None:
    executing = _execute(_queued())

    assert executing.state is OperationState.EXECUTING
    assert executing.attempts == 1
    assert executing.lease is not None
    assert executing.lease.worker_id == "worker-1"


def test_execution_is_refused_once_the_approval_has_expired() -> None:
    """Regression: queued work is not a standing permission to write."""
    queued = _queued()

    with pytest.raises(ApprovalExpiredError):
        _execute(queued, minutes=31)


def test_execution_is_refused_once_the_approval_is_revoked() -> None:
    queued = _queued()
    revoked = replace(queued, approval=queued.approval.revoke(at=at(minutes=2.5)))

    with pytest.raises(ApprovalRevokedError):
        _execute(revoked)


def test_execution_is_refused_with_an_approval_that_did_not_queue_the_operation() -> None:
    queued = _queued()
    other = replace(queued, approval=_approval(queued.plan, approval_id="approval-2"))

    with pytest.raises(OperationIdentityError):
        _execute(other)


def test_execution_is_refused_when_the_item_content_changed() -> None:
    """Same plan identifier and version, different content, so the payload differs."""
    queued = _queued()
    forged = make_plan(
        make_item("item-a", title="Rewritten activity"), make_item("item-b", start_hours=48)
    )

    with pytest.raises(OperationIdentityError):
        claim(
            queued.operation,
            approval=queued.approval,
            plan=forged,
            worker_id="worker-1",
            now=at(minutes=3),
            lease_duration=LEASE,
        )


def test_a_worker_cannot_claim_an_operation_another_worker_still_leases() -> None:
    """A stored row may still record a live lease when a second worker loads it."""
    queued = _queued()
    leased = replace(
        queued,
        operation=replace(
            queued.operation,
            lease=Lease(worker_id="worker-1", acquired_at=at(minutes=3), expires_at=at(minutes=8)),
        ),
    )

    with pytest.raises(LeaseHeldError):
        _execute(leased, worker_id="worker-2", minutes=4)


def test_a_worker_may_take_over_once_the_previous_lease_expired() -> None:
    queued = _queued()
    leased = replace(
        queued,
        operation=replace(
            queued.operation,
            lease=Lease(worker_id="worker-1", acquired_at=at(minutes=3), expires_at=at(minutes=8)),
        ),
    )

    taken = _execute(leased, worker_id="worker-2", minutes=9)

    assert taken.state is OperationState.EXECUTING
    assert taken.lease is not None
    assert taken.lease.worker_id == "worker-2"


def test_a_lost_response_yields_an_unknown_outcome_not_a_failure() -> None:
    unknown = record_ambiguous_outcome(
        _execute(_queued()), reason="provider timeout", now=at(minutes=4)
    )

    assert unknown.state is OperationState.OUTCOME_UNKNOWN
    assert unknown.external_ref is None


def test_an_expired_lease_is_not_evidence_that_the_write_failed() -> None:
    released = expire_lease(_execute(_queued()), now=at(minutes=9))

    assert released.state is OperationState.OUTCOME_UNKNOWN
    assert released.lease is None


def test_a_live_lease_cannot_be_expired_early() -> None:
    with pytest.raises(LeaseHeldError):
        expire_lease(_execute(_queued()), now=at(minutes=4))


def test_expiring_a_lease_is_refused_outside_execution() -> None:
    with pytest.raises(InvalidTransitionError):
        expire_lease(_queued().operation, now=at(minutes=9))


def test_an_executing_operation_without_a_lease_is_reported_explicitly() -> None:
    """Guards against a stored row that lost its lease record."""
    executing = _execute(_queued())

    with pytest.raises(LeaseNotHeldError):
        expire_lease(replace(executing, lease=None), now=at(minutes=9))


def test_an_unknown_outcome_cannot_be_retried_before_reconciliation() -> None:
    unknown = record_ambiguous_outcome(_execute(_queued()), reason="timeout", now=at(minutes=4))

    with pytest.raises(ReconciliationRequiredError):
        retry(unknown, now=at(minutes=5))


def test_reconciliation_adopts_a_write_the_provider_already_applied() -> None:
    unknown = record_ambiguous_outcome(_execute(_queued()), reason="timeout", now=at(minutes=4))
    resolved = reconcile(
        unknown,
        outcome=ProviderOutcome(applied=True, external_ref="evt-synthetic-1"),
        now=at(minutes=5),
    )

    assert resolved.state is OperationState.SUCCEEDED
    assert resolved.external_ref == "evt-synthetic-1"
    assert resolved.attempts == 1, "reconciliation must not consume a second attempt"


def test_reconciliation_reports_an_unapplied_write_as_a_retryable_failure() -> None:
    unknown = record_ambiguous_outcome(_execute(_queued()), reason="timeout", now=at(minutes=4))
    resolved = reconcile(unknown, outcome=ProviderOutcome(applied=False), now=at(minutes=5))

    assert resolved.state is OperationState.FAILED
    assert retry(resolved, now=at(minutes=6)).state is OperationState.QUEUED


def test_reconciling_a_settled_operation_is_refused() -> None:
    succeeded = record_success(_execute(_queued()), external_ref="evt-1", now=at(minutes=4))

    with pytest.raises(InvalidTransitionError):
        reconcile(
            succeeded,
            outcome=ProviderOutcome(applied=True, external_ref="evt-1"),
            now=at(minutes=5),
        )


def test_an_applied_outcome_must_carry_a_reference() -> None:
    with pytest.raises(ValidationError):
        ProviderOutcome(applied=True)
    with pytest.raises(ValidationError):
        ProviderOutcome(applied=False, external_ref="evt-1")


def test_the_idempotency_key_is_stable_across_attempts() -> None:
    queued = _queued()
    first = _execute(queued)
    failed = record_failure(first, reason="rate limited", now=at(minutes=4))
    requeued = retry(failed, now=at(minutes=5))
    second = _execute(replace(queued, operation=requeued), worker_id="worker-2", minutes=6)

    assert second.attempts == 2
    assert second.idempotency_key == queued.operation.idempotency_key


def test_the_retry_budget_bounds_the_number_of_attempts() -> None:
    queued = _queued()
    failed = record_failure(_execute(queued), reason="rate limited", now=at(minutes=4))

    for minute in (5, 7):
        requeued = retry(failed, now=at(minutes=minute))
        attempt = _execute(replace(queued, operation=requeued), minutes=minute + 0.5)
        failed = record_failure(attempt, reason="rate limited", now=at(minutes=minute + 1))

    assert failed.attempts == 3
    with pytest.raises(RetryBudgetExhaustedError):
        retry(failed, now=at(minutes=10))


def test_a_succeeded_operation_cannot_be_cancelled_in_place() -> None:
    succeeded = record_success(_execute(_queued()), external_ref="evt-1", now=at(minutes=4))

    assert succeeded.is_terminal
    with pytest.raises(InvalidTransitionError):
        cancel(succeeded, now=at(minutes=5))


def test_a_queued_operation_may_still_be_cancelled() -> None:
    cancelled = cancel(_queued().operation, now=at(minutes=3))

    assert cancelled.state is OperationState.CANCELLED
    assert cancelled.is_terminal


def test_a_compensating_operation_references_the_write_it_undoes() -> None:
    plan = _plan()
    compensating = propose(
        operation_id=OperationId("op-2"),
        plan=plan,
        item_id=ITEM,
        kind=OperationKind.CANCEL_EVENT,
        now=at(minutes=5),
        compensates=OperationId("op-1"),
    )

    assert compensating.compensates == "op-1"
    assert compensating.state is OperationState.PROPOSED
