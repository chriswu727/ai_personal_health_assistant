"""Lifecycle of a single external write, including ambiguous outcomes.

Three rules drive this module. Each is stated in the architecture and enforced
here rather than left to caller discipline:

* A lost or timed-out response is not a failure. It moves the operation to
  ``OUTCOME_UNKNOWN``, from which only reconciliation against the provider can
  produce a terminal state.
* An expired worker lease is not evidence that the external write failed. It
  also yields ``OUTCOME_UNKNOWN``.
* Every attempt of one operation presents the same idempotency key, so a
  provider that honors it collapses duplicate deliveries into one resource.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from health_assistant.domain.approvals import Approval, authorize_execution, fingerprint_items
from health_assistant.domain.errors import (
    InvalidTransitionError,
    LeaseHeldError,
    LeaseNotHeldError,
    ReconciliationRequiredError,
    RetryBudgetExhaustedError,
    ValidationError,
)
from health_assistant.domain.identifiers import (
    ApprovalId,
    OperationId,
    PlanId,
    PlanItemId,
    UserId,
    require_identifier,
)
from health_assistant.domain.plans import PlanVersion
from health_assistant.domain.scheduling import require_utc


class OperationState(StrEnum):
    PROPOSED = "proposed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"


class OperationKind(StrEnum):
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    CANCEL_EVENT = "cancel_event"


TERMINAL_STATES = frozenset({OperationState.SUCCEEDED, OperationState.CANCELLED})

ALLOWED_TRANSITIONS: Mapping[OperationState, frozenset[OperationState]] = MappingProxyType(
    {
        OperationState.PROPOSED: frozenset(
            {OperationState.AWAITING_CONFIRMATION, OperationState.CANCELLED}
        ),
        OperationState.AWAITING_CONFIRMATION: frozenset(
            {OperationState.QUEUED, OperationState.CANCELLED}
        ),
        OperationState.QUEUED: frozenset({OperationState.EXECUTING, OperationState.CANCELLED}),
        OperationState.EXECUTING: frozenset(
            {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.OUTCOME_UNKNOWN}
        ),
        # A verified failure may be retried; an unknown outcome may not.
        OperationState.FAILED: frozenset({OperationState.QUEUED, OperationState.CANCELLED}),
        OperationState.OUTCOME_UNKNOWN: frozenset(
            {OperationState.SUCCEEDED, OperationState.FAILED}
        ),
        OperationState.SUCCEEDED: frozenset(),
        OperationState.CANCELLED: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class Lease:
    """A time-bounded claim held by one worker."""

    worker_id: str
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "worker_id", require_identifier(self.worker_id, "worker_id"))
        object.__setattr__(self, "acquired_at", require_utc(self.acquired_at, "acquired_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))
        if self.expires_at <= self.acquired_at:
            raise ValidationError("lease expiry must follow acquisition")

    def is_expired_at(self, instant: datetime) -> bool:
        return require_utc(instant, "instant") >= self.expires_at


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """What the provider reports when an ambiguous operation is reconciled."""

    applied: bool
    external_ref: str | None = None

    def __post_init__(self) -> None:
        reference = (self.external_ref or "").strip()
        if self.applied and not reference:
            raise ValidationError("an applied outcome must carry the external reference")
        if not self.applied and self.external_ref is not None:
            raise ValidationError("an unapplied outcome must not carry an external reference")


def derive_idempotency_key(operation_id: OperationId, payload_fingerprint: str) -> str:
    """Return a key that is stable across every attempt of the same operation."""
    digest = hashlib.sha256(f"{operation_id}:{payload_fingerprint}".encode()).hexdigest()
    return digest[:32]


@dataclass(frozen=True, slots=True)
class ToolOperation:
    """One external write request and everything known about its outcome."""

    operation_id: OperationId
    owner_id: UserId
    plan_id: PlanId
    plan_version: int
    item_id: PlanItemId
    kind: OperationKind
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    state: OperationState = OperationState.PROPOSED
    approval_id: ApprovalId | None = None
    attempts: int = 0
    retry_budget: int = 3
    lease: Lease | None = None
    external_ref: str | None = None
    last_error: str | None = None
    compensates: OperationId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operation_id", require_identifier(self.operation_id, "operation_id")
        )
        object.__setattr__(self, "owner_id", require_identifier(self.owner_id, "owner_id"))
        object.__setattr__(self, "plan_id", require_identifier(self.plan_id, "plan_id"))
        object.__setattr__(self, "item_id", require_identifier(self.item_id, "item_id"))
        object.__setattr__(
            self, "idempotency_key", require_identifier(self.idempotency_key, "idempotency_key")
        )
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", require_utc(self.updated_at, "updated_at"))
        if self.retry_budget < 1:
            raise ValidationError("retry budget must allow at least one attempt")
        if self.attempts < 0:
            raise ValidationError("attempt count must not be negative")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


def _ensure_transition(operation: ToolOperation, target: OperationState) -> None:
    """Raise unless the state machine permits moving to ``target``."""
    if target not in ALLOWED_TRANSITIONS[operation.state]:
        raise InvalidTransitionError(str(operation.state), str(target))


def propose(
    *,
    operation_id: OperationId,
    plan: PlanVersion,
    item_id: PlanItemId,
    kind: OperationKind,
    now: datetime,
    retry_budget: int = 3,
    compensates: OperationId | None = None,
) -> ToolOperation:
    """Create an operation for one still-proposed item at this exact plan version."""
    item = plan.item(item_id)
    if item.is_reported:
        raise ValidationError("an item with a reported outcome cannot be executed externally")
    instant = require_utc(now, "now")
    return ToolOperation(
        operation_id=operation_id,
        owner_id=plan.owner_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        item_id=item_id,
        kind=kind,
        idempotency_key=derive_idempotency_key(operation_id, fingerprint_items([item])),
        created_at=instant,
        updated_at=instant,
        state=OperationState.PROPOSED,
        retry_budget=retry_budget,
        compensates=compensates,
    )


def request_confirmation(operation: ToolOperation, *, now: datetime) -> ToolOperation:
    """Present the proposal to the user and wait for an explicit decision."""
    _ensure_transition(operation, OperationState.AWAITING_CONFIRMATION)
    return replace(
        operation,
        state=OperationState.AWAITING_CONFIRMATION,
        updated_at=require_utc(now, "now"),
    )


def confirm(
    operation: ToolOperation,
    *,
    approval: Approval,
    plan: PlanVersion,
    actor_id: UserId,
    now: datetime,
) -> ToolOperation:
    """Queue the operation only if the approval still authorizes this exact item."""
    _ensure_transition(operation, OperationState.QUEUED)
    if operation.plan_version != plan.version:
        raise ValidationError("operation refers to a different plan version than the plan given")
    authorize_execution(
        approval,
        plan=plan,
        item_ids=frozenset({operation.item_id}),
        actor_id=actor_id,
        now=now,
    )
    return replace(
        operation,
        state=OperationState.QUEUED,
        approval_id=approval.approval_id,
        updated_at=require_utc(now, "now"),
    )


def claim(
    operation: ToolOperation,
    *,
    worker_id: str,
    now: datetime,
    lease_duration: timedelta,
) -> ToolOperation:
    """Take the operation for execution under a time-bounded lease."""
    _ensure_transition(operation, OperationState.EXECUTING)
    instant = require_utc(now, "now")
    held = operation.lease
    if held is not None and not held.is_expired_at(instant) and held.worker_id != worker_id:
        raise LeaseHeldError(held.worker_id)
    if operation.attempts >= operation.retry_budget:
        raise RetryBudgetExhaustedError(operation.retry_budget)
    return replace(
        operation,
        state=OperationState.EXECUTING,
        lease=Lease(worker_id=worker_id, acquired_at=instant, expires_at=instant + lease_duration),
        attempts=operation.attempts + 1,
        updated_at=instant,
    )


def record_success(operation: ToolOperation, *, external_ref: str, now: datetime) -> ToolOperation:
    """Record a write the provider confirmed, together with its resource reference."""
    _ensure_transition(operation, OperationState.SUCCEEDED)
    if not external_ref.strip():
        raise ValidationError("a successful write must record the external reference")
    return replace(
        operation,
        state=OperationState.SUCCEEDED,
        external_ref=external_ref,
        lease=None,
        last_error=None,
        updated_at=require_utc(now, "now"),
    )


def record_failure(operation: ToolOperation, *, reason: str, now: datetime) -> ToolOperation:
    """Record a failure the provider confirmed, which may later be retried."""
    _ensure_transition(operation, OperationState.FAILED)
    return replace(
        operation,
        state=OperationState.FAILED,
        lease=None,
        last_error=reason,
        updated_at=require_utc(now, "now"),
    )


def record_ambiguous_outcome(
    operation: ToolOperation, *, reason: str, now: datetime
) -> ToolOperation:
    """Record that the provider's response was lost, timed out, or unreadable."""
    _ensure_transition(operation, OperationState.OUTCOME_UNKNOWN)
    return replace(
        operation,
        state=OperationState.OUTCOME_UNKNOWN,
        lease=None,
        last_error=reason,
        updated_at=require_utc(now, "now"),
    )


def expire_lease(operation: ToolOperation, *, now: datetime) -> ToolOperation:
    """Release an expired lease without asserting that the external write failed."""
    _ensure_transition(operation, OperationState.OUTCOME_UNKNOWN)
    lease = operation.lease
    if lease is None:
        raise LeaseNotHeldError()
    if not lease.is_expired_at(now):
        raise LeaseHeldError(lease.worker_id)
    return replace(
        operation,
        state=OperationState.OUTCOME_UNKNOWN,
        lease=None,
        last_error=f"lease held by {lease.worker_id} expired during execution",
        updated_at=require_utc(now, "now"),
    )


def reconcile(
    operation: ToolOperation, *, outcome: ProviderOutcome, now: datetime
) -> ToolOperation:
    """Resolve an ambiguous outcome using observed provider state."""
    if operation.state is not OperationState.OUTCOME_UNKNOWN:
        raise InvalidTransitionError(str(operation.state), "reconciled")
    instant = require_utc(now, "now")
    if outcome.applied:
        return replace(
            operation,
            state=OperationState.SUCCEEDED,
            external_ref=outcome.external_ref,
            last_error=None,
            updated_at=instant,
        )
    return replace(
        operation,
        state=OperationState.FAILED,
        last_error="provider reported the write was not applied",
        updated_at=instant,
    )


def retry(operation: ToolOperation, *, now: datetime) -> ToolOperation:
    """Re-queue a confirmed failure, refusing to retry an unknown outcome."""
    if operation.state is OperationState.OUTCOME_UNKNOWN:
        raise ReconciliationRequiredError()
    _ensure_transition(operation, OperationState.QUEUED)
    if operation.attempts >= operation.retry_budget:
        raise RetryBudgetExhaustedError(operation.retry_budget)
    return replace(operation, state=OperationState.QUEUED, updated_at=require_utc(now, "now"))


def cancel(operation: ToolOperation, *, now: datetime) -> ToolOperation:
    """Cancel work that has not been applied externally.

    A succeeded operation is terminal: undoing a confirmed remote write requires
    a separately authorized compensating operation, not a state change here.
    """
    _ensure_transition(operation, OperationState.CANCELLED)
    return replace(
        operation,
        state=OperationState.CANCELLED,
        lease=None,
        updated_at=require_utc(now, "now"),
    )
