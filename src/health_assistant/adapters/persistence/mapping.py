"""Translation between domain values and database rows.

The domain never sees a row and the schema never sees a domain object; this
module is the only place that knows both shapes.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from health_assistant.domain.actions import ApprovedAction, OperationKind
from health_assistant.domain.approvals import Approval
from health_assistant.domain.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSeverity,
    ConstraintSource,
)
from health_assistant.domain.identifiers import (
    ApprovalId,
    ConstraintId,
    OperationId,
    PlanId,
    PlanItemId,
    UserId,
)
from health_assistant.domain.operations import (
    Lease,
    OperationState,
    ToolOperation,
)
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItem,
    PlanItemCategory,
    PlanVersion,
)
from health_assistant.domain.scheduling import TimeWindow, require_utc


def plan_row(version: PlanVersion) -> dict[str, Any]:
    return {
        "plan_id": version.plan_id,
        "owner_id": version.owner_id,
        "created_at": version.created_at,
    }


def plan_version_row(version: PlanVersion) -> dict[str, Any]:
    return {
        "plan_id": version.plan_id,
        "version": version.version,
        "owner_id": version.owner_id,
        "parent_version": version.parent_version,
        "created_at": version.created_at,
    }


def plan_item_rows(version: PlanVersion) -> list[dict[str, Any]]:
    return [
        {
            "plan_id": version.plan_id,
            "version": version.version,
            "item_id": item.item_id,
            "owner_id": version.owner_id,
            "category": str(item.category),
            "title": item.title,
            "starts_at": item.window.start,
            "ends_at": item.window.end,
            "time_zone": item.window.time_zone,
            # Sorted so that a stored row is byte-comparable across writes.
            "attributes": sorted(item.attributes),
            "completion": str(item.completion),
        }
        for item in version.items
    ]


def to_plan_item(row: Mapping[str, Any]) -> PlanItem:
    return PlanItem(
        item_id=PlanItemId(row["item_id"]),
        category=PlanItemCategory(row["category"]),
        title=row["title"],
        window=TimeWindow(
            start=require_utc(row["starts_at"], "starts_at"),
            end=require_utc(row["ends_at"], "ends_at"),
            time_zone=row["time_zone"],
        ),
        attributes=frozenset(row["attributes"]),
        completion=CompletionStatus(row["completion"]),
    )


def to_plan_version(
    version_row: Mapping[str, Any], item_rows: Sequence[Mapping[str, Any]]
) -> PlanVersion:
    return PlanVersion(
        plan_id=PlanId(version_row["plan_id"]),
        owner_id=UserId(version_row["owner_id"]),
        version=version_row["version"],
        items=tuple(to_plan_item(row) for row in item_rows),
        created_at=require_utc(version_row["created_at"], "created_at"),
        parent_version=version_row["parent_version"],
    )


# "No compensation target" is stored as an empty string rather than NULL,
# because PostgreSQL treats NULLs as distinct inside a key.
NO_TARGET = ""


def constraint_row(constraint: Constraint) -> dict[str, Any]:
    window = constraint.window
    return {
        "constraint_id": constraint.constraint_id,
        "owner_id": constraint.owner_id,
        "kind": str(constraint.kind),
        "severity": str(constraint.severity),
        "source": str(constraint.source),
        "subject": constraint.subject,
        "window_starts_at": window.start if window is not None else None,
        "window_ends_at": window.end if window is not None else None,
        "window_time_zone": window.time_zone if window is not None else None,
        "recorded_at": constraint.recorded_at,
        "expires_at": constraint.expires_at,
    }


def to_constraint(row: Mapping[str, Any]) -> Constraint:
    window = None
    if row["window_starts_at"] is not None:
        window = TimeWindow(
            start=require_utc(row["window_starts_at"], "window_starts_at"),
            end=require_utc(row["window_ends_at"], "window_ends_at"),
            time_zone=row["window_time_zone"],
        )
    return Constraint(
        constraint_id=ConstraintId(row["constraint_id"]),
        owner_id=UserId(row["owner_id"]),
        kind=ConstraintKind(row["kind"]),
        severity=ConstraintSeverity(row["severity"]),
        source=ConstraintSource(row["source"]),
        recorded_at=require_utc(row["recorded_at"], "recorded_at"),
        subject=row["subject"],
        window=window,
        expires_at=row["expires_at"],
    )


def approval_row(approval: Approval) -> dict[str, Any]:
    return {
        "approval_id": approval.approval_id,
        "owner_id": approval.owner_id,
        "plan_id": approval.plan_id,
        "plan_version": approval.plan_version,
        "payload_fingerprint": approval.payload_fingerprint,
        "granted_at": approval.granted_at,
        "expires_at": approval.expires_at,
        "revoked_at": approval.revoked_at,
    }


def approval_action_rows(approval: Approval) -> list[dict[str, Any]]:
    return [
        {
            "approval_id": approval.approval_id,
            "item_id": action.item_id,
            "kind": str(action.kind),
            "compensates": action.compensates or NO_TARGET,
        }
        for action in approval.scope
    ]


def to_approval(row: Mapping[str, Any], action_rows: Sequence[Mapping[str, Any]]) -> Approval:
    return Approval(
        approval_id=ApprovalId(row["approval_id"]),
        owner_id=UserId(row["owner_id"]),
        plan_id=PlanId(row["plan_id"]),
        plan_version=row["plan_version"],
        scope=frozenset(to_approved_action(action) for action in action_rows),
        payload_fingerprint=row["payload_fingerprint"],
        granted_at=require_utc(row["granted_at"], "granted_at"),
        expires_at=require_utc(row["expires_at"], "expires_at"),
        revoked_at=row["revoked_at"],
    )


def to_approved_action(row: Mapping[str, Any]) -> ApprovedAction:
    target = row["compensates"]
    return ApprovedAction(
        item_id=PlanItemId(row["item_id"]),
        kind=OperationKind(row["kind"]),
        compensates=OperationId(target) if target != NO_TARGET else None,
    )


def operation_row(operation: ToolOperation) -> dict[str, Any]:
    lease = operation.lease
    return {
        "operation_id": operation.operation_id,
        "owner_id": operation.owner_id,
        "plan_id": operation.plan_id,
        "plan_version": operation.plan_version,
        "item_id": operation.item_id,
        "kind": str(operation.kind),
        "compensates": operation.compensates,
        "idempotency_key": operation.idempotency_key,
        "state": str(operation.state),
        "approval_id": operation.approval_id,
        "attempts": operation.attempts,
        "retry_budget": operation.retry_budget,
        "lease_worker_id": lease.worker_id if lease is not None else None,
        "lease_acquired_at": lease.acquired_at if lease is not None else None,
        "lease_expires_at": lease.expires_at if lease is not None else None,
        "external_ref": operation.external_ref,
        "last_error": operation.last_error,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
    }


def to_operation(row: Mapping[str, Any]) -> ToolOperation:
    lease = None
    if row["lease_worker_id"] is not None:
        lease = Lease(
            worker_id=row["lease_worker_id"],
            acquired_at=require_utc(row["lease_acquired_at"], "lease_acquired_at"),
            expires_at=require_utc(row["lease_expires_at"], "lease_expires_at"),
        )
    target = row["compensates"]
    approval = row["approval_id"]
    return ToolOperation(
        operation_id=OperationId(row["operation_id"]),
        owner_id=UserId(row["owner_id"]),
        plan_id=PlanId(row["plan_id"]),
        plan_version=row["plan_version"],
        item_id=PlanItemId(row["item_id"]),
        kind=OperationKind(row["kind"]),
        idempotency_key=row["idempotency_key"],
        created_at=require_utc(row["created_at"], "created_at"),
        updated_at=require_utc(row["updated_at"], "updated_at"),
        state=OperationState(row["state"]),
        approval_id=ApprovalId(approval) if approval is not None else None,
        attempts=row["attempts"],
        retry_budget=row["retry_budget"],
        lease=lease,
        external_ref=row["external_ref"],
        last_error=row["last_error"],
        compensates=OperationId(target) if target is not None else None,
    )
