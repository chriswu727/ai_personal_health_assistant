"""Distinct identifier types for user-owned domain entities."""

from typing import NewType

from health_assistant.domain.errors import EmptyIdentifierError

UserId = NewType("UserId", str)
PlanId = NewType("PlanId", str)
PlanItemId = NewType("PlanItemId", str)
ConstraintId = NewType("ConstraintId", str)
ApprovalId = NewType("ApprovalId", str)
OperationId = NewType("OperationId", str)


def require_identifier(value: str, field: str) -> str:
    """Return the stripped identifier, rejecting blank values."""
    stripped = value.strip()
    if not stripped:
        raise EmptyIdentifierError(field)
    return stripped
