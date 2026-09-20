"""User confirmation bound to an exact payload, action, scope, and expiry.

An approval authorizes one named external action per plan item, at one plan
version whose content hashes to a recorded fingerprint. Any later revision
produces a new version, so an earlier confirmation can never authorize content
the user did not see, and a confirmation to create an event never authorizes
cancelling one.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from health_assistant.domain.actions import ApprovedAction, action_sort_key
from health_assistant.domain.constraints import ConstraintSet
from health_assistant.domain.errors import (
    ApprovalActionNotAuthorizedError,
    ApprovalExpiredError,
    ApprovalPayloadChangedError,
    ApprovalRevokedError,
    ApprovalScopeError,
    ApprovalTargetMismatchError,
    ApprovalVersionMismatchError,
    OwnershipError,
    PlanNotApprovableError,
    ValidationError,
)
from health_assistant.domain.identifiers import (
    ApprovalId,
    PlanId,
    PlanItemId,
    UserId,
    require_identifier,
)
from health_assistant.domain.plans import PlanItem, PlanVersion
from health_assistant.domain.scheduling import require_utc
from health_assistant.domain.validation import ValidationReport, validate_plan


def _item_payload(item: PlanItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "category": str(item.category),
        "title": item.title,
        "start": item.window.start.isoformat(),
        "end": item.window.end.isoformat(),
        "time_zone": item.window.time_zone,
        "attributes": sorted(item.attributes),
        "completion": str(item.completion),
    }


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_items(items: Iterable[PlanItem]) -> str:
    """Return a stable digest over the user-visible content of ``items``.

    Ordering of items and of attribute tokens must not change the digest, so the
    same proposal always produces the same fingerprint on any machine.
    """
    return _digest([_item_payload(item) for item in sorted(items, key=lambda item: item.item_id)])


def _action_payload(plan: PlanVersion, action: ApprovedAction) -> dict[str, object]:
    return {
        "kind": str(action.kind),
        "compensates": action.compensates,
        "item": _item_payload(plan.item(action.item_id)),
    }


def fingerprint_action(plan: PlanVersion, action: ApprovedAction) -> str:
    """Return a digest of one approved action, its target, and its item content.

    This is the canonical description of a single external write. An operation
    derives its idempotency key from it, and an approval's fingerprint is built
    from the same payloads, so both detect the same substitutions.
    """
    return _digest(_action_payload(plan, action))


def fingerprint_scope(plan: PlanVersion, scope: Iterable[ApprovedAction]) -> str:
    """Return a digest over the approved content, actions, and action targets.

    Including the action and its target means a confirmation for one external
    write cannot be replayed to authorize a different kind of write, or the same
    kind of write against a different target.
    """
    return _digest([_action_payload(plan, action) for action in sorted(scope, key=action_sort_key)])


@dataclass(frozen=True, slots=True)
class Approval:
    """A confirmation valid only for named actions on one payload at one version."""

    approval_id: ApprovalId
    owner_id: UserId
    plan_id: PlanId
    plan_version: int
    scope: frozenset[ApprovedAction]
    payload_fingerprint: str
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", require_identifier(self.approval_id, "approval_id"))
        object.__setattr__(self, "owner_id", require_identifier(self.owner_id, "owner_id"))
        object.__setattr__(self, "plan_id", require_identifier(self.plan_id, "plan_id"))
        object.__setattr__(self, "granted_at", require_utc(self.granted_at, "granted_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))
        if self.revoked_at is not None:
            object.__setattr__(self, "revoked_at", require_utc(self.revoked_at, "revoked_at"))
        if not self.scope:
            raise ValidationError("an approval must cover at least one action")
        if self.expires_at <= self.granted_at:
            raise ValidationError("approval expiry must follow the grant instant")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def item_ids(self) -> frozenset[PlanItemId]:
        return frozenset(action.item_id for action in self.scope)

    def is_expired_at(self, instant: datetime) -> bool:
        return require_utc(instant, "instant") >= self.expires_at

    def revoke(self, *, at: datetime) -> "Approval":
        if self.is_revoked:
            return self
        return replace(self, revoked_at=require_utc(at, "at"))


def grant_approval(
    *,
    approval_id: ApprovalId,
    plan: PlanVersion,
    constraints: ConstraintSet,
    scope: frozenset[ApprovedAction],
    actor_id: UserId,
    now: datetime,
    ttl: timedelta,
) -> Approval:
    """Record a confirmation for ``scope``, refusing blocked or invalid scopes.

    Constraint validation runs here rather than in a caller so that no execution
    path can obtain an approval for a plan that violates a hard constraint.
    """
    if actor_id != plan.owner_id:
        raise OwnershipError(f"user {actor_id!r} may not approve plan {plan.plan_id!r}")
    if not scope:
        raise ApprovalScopeError("approval scope must name at least one action")
    if ttl <= timedelta(0):
        raise ValidationError("approval ttl must be positive")

    item_ids = frozenset(action.item_id for action in scope)
    unknown = item_ids - plan.item_ids()
    if unknown:
        raise ApprovalScopeError(f"scope names items absent from this version: {sorted(unknown)}")

    scoped_items = tuple(item for item in plan.items if item.item_id in item_ids)
    reported = [item.item_id for item in scoped_items if item.is_reported]
    if reported:
        raise ApprovalScopeError(f"scope names items with reported outcomes: {sorted(reported)}")

    report = validate_plan(plan, constraints, at=now).for_items(item_ids)
    if report.is_blocking:
        details = "; ".join(
            f"{finding.item_id}: {finding.outcome} ({finding.detail})"
            for finding in report.blocking
        )
        raise PlanNotApprovableError(f"blocking constraint findings: {details}")

    granted_at = require_utc(now, "now")
    return Approval(
        approval_id=approval_id,
        owner_id=plan.owner_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        scope=frozenset(scope),
        payload_fingerprint=fingerprint_scope(plan, scope),
        granted_at=granted_at,
        expires_at=granted_at + ttl,
    )


def authorize_execution(
    approval: Approval,
    *,
    plan: PlanVersion,
    actions: frozenset[ApprovedAction],
    actor_id: UserId,
    now: datetime,
) -> None:
    """Raise unless ``approval`` still authorizes every action in ``actions``.

    Checks run from cheapest and most specific to the content comparison, so the
    raised error names the actual reason rather than a generic failure.
    """
    if approval.owner_id != actor_id or plan.owner_id != actor_id:
        raise OwnershipError("approval, plan, and actor must refer to the same user")
    if approval.plan_id != plan.plan_id:
        raise ApprovalScopeError("approval refers to a different plan")
    if approval.is_revoked:
        raise ApprovalRevokedError()
    if approval.is_expired_at(now):
        raise ApprovalExpiredError()
    if approval.plan_version != plan.version:
        raise ApprovalVersionMismatchError(approved=approval.plan_version, requested=plan.version)
    if not actions:
        raise ApprovalScopeError("at least one action must be requested")

    for action in sorted(actions, key=action_sort_key):
        if action in approval.scope:
            continue
        if action.item_id not in approval.item_ids:
            raise ApprovalScopeError(f"item outside the approved scope: {action.item_id!r}")
        same_kind = any(
            approved.item_id == action.item_id and approved.kind == action.kind
            for approved in approval.scope
        )
        if same_kind:
            raise ApprovalTargetMismatchError(action.item_id, str(action.kind), action.compensates)
        raise ApprovalActionNotAuthorizedError(action.item_id, str(action.kind))

    if fingerprint_scope(plan, approval.scope) != approval.payload_fingerprint:
        raise ApprovalPayloadChangedError()


def validation_report_for(
    plan: PlanVersion, constraints: ConstraintSet, *, at: datetime
) -> ValidationReport:
    """Convenience wrapper so callers can preview findings before approving."""
    return validate_plan(plan, constraints, at=at)
