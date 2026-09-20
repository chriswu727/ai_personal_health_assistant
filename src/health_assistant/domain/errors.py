"""Explicit error categories raised by the domain.

Callers distinguish input problems, authorization problems, and lifecycle
problems by type rather than by parsing messages.
"""


class DomainError(Exception):
    """Base class for every error raised by domain code."""


class ValidationError(DomainError):
    """Input violates a domain invariant."""


class EmptyIdentifierError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} must be a non-empty identifier")
        self.field = field


class NaiveDatetimeError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} must be timezone-aware")
        self.field = field


class InvalidTimeRangeError(ValidationError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class UnknownTimeZoneError(ValidationError):
    def __init__(self, time_zone: str) -> None:
        super().__init__(f"unknown IANA time zone: {time_zone!r}")
        self.time_zone = time_zone


class OwnershipError(DomainError):
    """An actor attempted to act on an entity owned by someone else."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class PlanError(DomainError):
    """Base class for plan revision failures."""


class EmptyRevisionError(PlanError):
    def __init__(self) -> None:
        super().__init__("a revision must contain at least one change")


class StalePlanRevisionError(PlanError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected plan version {expected}, found {actual}")
        self.expected = expected
        self.actual = actual


class UnknownPlanItemError(PlanError):
    def __init__(self, item_id: str) -> None:
        super().__init__(f"plan item {item_id!r} does not exist in this version")
        self.item_id = item_id


class DuplicatePlanItemError(PlanError):
    def __init__(self, item_id: str) -> None:
        super().__init__(f"plan item {item_id!r} already exists in this version")
        self.item_id = item_id


class CompletedHistoryError(PlanError):
    """A revision attempted to rewrite a reported outcome."""

    def __init__(self, item_id: str) -> None:
        super().__init__(f"plan item {item_id!r} has a reported outcome and is immutable history")
        self.item_id = item_id


class ApprovalError(DomainError):
    """Base class for approval authorization failures."""


class PlanNotApprovableError(ApprovalError):
    """Blocking constraint findings prevent approval of the requested scope."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ApprovalExpiredError(ApprovalError):
    def __init__(self) -> None:
        super().__init__("approval has expired")


class ApprovalRevokedError(ApprovalError):
    def __init__(self) -> None:
        super().__init__("approval has been revoked")


class ApprovalVersionMismatchError(ApprovalError):
    def __init__(self, approved: int, requested: int) -> None:
        super().__init__(
            f"approval covers plan version {approved}, execution requested version {requested}"
        )
        self.approved = approved
        self.requested = requested


class ApprovalPayloadChangedError(ApprovalError):
    def __init__(self) -> None:
        super().__init__("approved payload no longer matches the plan content")


class ApprovalScopeError(ApprovalError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class OperationError(DomainError):
    """Base class for external-operation lifecycle failures."""


class InvalidTransitionError(OperationError):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"transition {source} -> {target} is not permitted")
        self.source = source
        self.target = target


class ReconciliationRequiredError(OperationError):
    """An ambiguous outcome must be resolved against the provider before any retry."""

    def __init__(self) -> None:
        super().__init__(
            "operation outcome is unknown; reconcile provider state before retrying a write"
        )


class RetryBudgetExhaustedError(OperationError):
    def __init__(self, budget: int) -> None:
        super().__init__(f"retry budget of {budget} attempts is exhausted")
        self.budget = budget


class LeaseHeldError(OperationError):
    def __init__(self, worker_id: str) -> None:
        super().__init__(f"operation lease is held by worker {worker_id!r}")
        self.worker_id = worker_id


class LeaseNotHeldError(OperationError):
    def __init__(self) -> None:
        super().__init__("operation is not currently leased")
