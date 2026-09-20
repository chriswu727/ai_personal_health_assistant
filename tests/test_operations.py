"""External operation lifecycle, including ambiguous outcomes and leases."""

from dataclasses import replace
from datetime import timedelta

import pytest

from health_assistant.domain.approvals import grant_approval
from health_assistant.domain.errors import (
    ApprovalExpiredError,
    InvalidTransitionError,
    LeaseHeldError,
    LeaseNotHeldError,
    ReconciliationRequiredError,
    RetryBudgetExhaustedError,
    ValidationError,
)
from health_assistant.domain.identifiers import ApprovalId, OperationId, PlanItemId
from health_assistant.domain.operations import (
    ALLOWED_TRANSITIONS,
    Lease,
    OperationKind,
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
from tests.support import EMPTY_CONSTRAINTS, OWNER, at, make_item, make_plan

TTL = timedelta(minutes=30)
LEASE = timedelta(minutes=5)
SCOPE = frozenset({PlanItemId("item-a")})


def _plan() -> PlanVersion:
    return make_plan(make_item("item-a"), make_item("item-b", start_hours=48))


def _queued(plan: PlanVersion) -> ToolOperation:
    approval = grant_approval(
        approval_id=ApprovalId("approval-1"),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=SCOPE,
        actor_id=OWNER,
        now=at(),
        ttl=TTL,
    )
    operation = propose(
        operation_id=OperationId("op-1"),
        plan=plan,
        item_id=PlanItemId("item-a"),
        kind=OperationKind.CREATE_EVENT,
        now=at(),
    )
    awaiting = request_confirmation(operation, now=at(minutes=1))
    return confirm(awaiting, approval=approval, plan=plan, actor_id=OWNER, now=at(minutes=2))


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
            item_id=PlanItemId("item-a"),
            kind=OperationKind.CREATE_EVENT,
            now=at(),
        )


def test_confirmation_requires_a_valid_approval() -> None:
    plan = _plan()
    approval = grant_approval(
        approval_id=ApprovalId("approval-1"),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=SCOPE,
        actor_id=OWNER,
        now=at(),
        ttl=TTL,
    )
    awaiting = request_confirmation(
        propose(
            operation_id=OperationId("op-1"),
            plan=plan,
            item_id=PlanItemId("item-a"),
            kind=OperationKind.CREATE_EVENT,
            now=at(),
        ),
        now=at(minutes=1),
    )

    with pytest.raises(ApprovalExpiredError):
        confirm(awaiting, approval=approval, plan=plan, actor_id=OWNER, now=at(minutes=31))
    assert awaiting.state is OperationState.AWAITING_CONFIRMATION


def test_queueing_without_passing_through_confirmation_is_refused() -> None:
    plan = _plan()
    approval = grant_approval(
        approval_id=ApprovalId("approval-1"),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=SCOPE,
        actor_id=OWNER,
        now=at(),
        ttl=TTL,
    )
    proposed = propose(
        operation_id=OperationId("op-1"),
        plan=plan,
        item_id=PlanItemId("item-a"),
        kind=OperationKind.CREATE_EVENT,
        now=at(),
    )

    with pytest.raises(InvalidTransitionError):
        confirm(proposed, approval=approval, plan=plan, actor_id=OWNER, now=at(minutes=2))


def test_claiming_records_an_attempt_and_a_lease() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )

    assert executing.state is OperationState.EXECUTING
    assert executing.attempts == 1
    assert executing.lease is not None
    assert executing.lease.worker_id == "worker-1"


def test_a_worker_cannot_claim_an_operation_another_worker_still_leases() -> None:
    """A stored row may still record a live lease when a second worker loads it."""
    queued = _queued(_plan())
    leased = replace(
        queued,
        lease=Lease(worker_id="worker-1", acquired_at=at(minutes=3), expires_at=at(minutes=8)),
    )

    with pytest.raises(LeaseHeldError):
        claim(leased, worker_id="worker-2", now=at(minutes=4), lease_duration=LEASE)


def test_a_worker_may_take_over_once_the_previous_lease_expired() -> None:
    queued = _queued(_plan())
    leased = replace(
        queued,
        lease=Lease(worker_id="worker-1", acquired_at=at(minutes=3), expires_at=at(minutes=8)),
    )

    taken = claim(leased, worker_id="worker-2", now=at(minutes=9), lease_duration=LEASE)

    assert taken.state is OperationState.EXECUTING
    assert taken.lease is not None
    assert taken.lease.worker_id == "worker-2"


def test_a_lost_response_yields_an_unknown_outcome_not_a_failure() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    unknown = record_ambiguous_outcome(executing, reason="provider timeout", now=at(minutes=4))

    assert unknown.state is OperationState.OUTCOME_UNKNOWN
    assert unknown.external_ref is None


def test_an_expired_lease_is_not_evidence_that_the_write_failed() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    released = expire_lease(executing, now=at(minutes=9))

    assert released.state is OperationState.OUTCOME_UNKNOWN
    assert released.lease is None


def test_a_live_lease_cannot_be_expired_early() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )

    with pytest.raises(LeaseHeldError):
        expire_lease(executing, now=at(minutes=4))


def test_expiring_a_lease_is_refused_outside_execution() -> None:
    queued = _queued(_plan())
    with pytest.raises(InvalidTransitionError):
        expire_lease(queued, now=at(minutes=9))


def test_an_executing_operation_without_a_lease_is_reported_explicitly() -> None:
    """Guards against a stored row that lost its lease record."""
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )

    with pytest.raises(LeaseNotHeldError):
        expire_lease(replace(executing, lease=None), now=at(minutes=9))


def test_an_unknown_outcome_cannot_be_retried_before_reconciliation() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    unknown = record_ambiguous_outcome(executing, reason="timeout", now=at(minutes=4))

    with pytest.raises(ReconciliationRequiredError):
        retry(unknown, now=at(minutes=5))


def test_reconciliation_adopts_a_write_the_provider_already_applied() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    unknown = record_ambiguous_outcome(executing, reason="timeout", now=at(minutes=4))
    resolved = reconcile(
        unknown,
        outcome=ProviderOutcome(applied=True, external_ref="evt-synthetic-1"),
        now=at(minutes=5),
    )

    assert resolved.state is OperationState.SUCCEEDED
    assert resolved.external_ref == "evt-synthetic-1"
    assert resolved.attempts == 1, "reconciliation must not consume a second attempt"


def test_reconciliation_reports_an_unapplied_write_as_a_retryable_failure() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    unknown = record_ambiguous_outcome(executing, reason="timeout", now=at(minutes=4))
    resolved = reconcile(unknown, outcome=ProviderOutcome(applied=False), now=at(minutes=5))

    assert resolved.state is OperationState.FAILED
    assert retry(resolved, now=at(minutes=6)).state is OperationState.QUEUED


def test_reconciling_a_settled_operation_is_refused() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    succeeded = record_success(executing, external_ref="evt-1", now=at(minutes=4))

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
    queued = _queued(_plan())
    first = claim(queued, worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE)
    failed = record_failure(first, reason="rate limited", now=at(minutes=4))
    requeued = retry(failed, now=at(minutes=5))
    second = claim(requeued, worker_id="worker-2", now=at(minutes=6), lease_duration=LEASE)

    assert second.attempts == 2
    assert second.idempotency_key == queued.idempotency_key


def test_the_retry_budget_bounds_the_number_of_attempts() -> None:
    plan = _plan()
    operation = _queued(plan)
    budgeted = claim(operation, worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE)
    failed = record_failure(budgeted, reason="rate limited", now=at(minutes=4))

    for minute in (5, 7):
        requeued = retry(failed, now=at(minutes=minute))
        attempt = claim(
            requeued,
            worker_id="worker-1",
            now=at(minutes=minute + 0.5),
            lease_duration=LEASE,
        )
        failed = record_failure(attempt, reason="rate limited", now=at(minutes=minute + 1))

    assert failed.attempts == 3
    with pytest.raises(RetryBudgetExhaustedError):
        retry(failed, now=at(minutes=10))


def test_a_succeeded_operation_cannot_be_cancelled_in_place() -> None:
    executing = claim(
        _queued(_plan()), worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
    )
    succeeded = record_success(executing, external_ref="evt-1", now=at(minutes=4))

    assert succeeded.is_terminal
    with pytest.raises(InvalidTransitionError):
        cancel(succeeded, now=at(minutes=5))


def test_a_queued_operation_may_still_be_cancelled() -> None:
    cancelled = cancel(_queued(_plan()), now=at(minutes=3))

    assert cancelled.state is OperationState.CANCELLED
    assert cancelled.is_terminal


def test_a_compensating_operation_references_the_write_it_undoes() -> None:
    plan = _plan()
    compensating = propose(
        operation_id=OperationId("op-2"),
        plan=plan,
        item_id=PlanItemId("item-a"),
        kind=OperationKind.CANCEL_EVENT,
        now=at(minutes=5),
        compensates=OperationId("op-1"),
    )

    assert compensating.compensates == "op-1"
    assert compensating.idempotency_key != _queued(plan).idempotency_key
