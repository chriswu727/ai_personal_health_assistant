"""User confirmation bound to an exact payload, scope, and expiry.

An approval authorizes external execution for named plan items at one plan
version whose content hashes to a recorded fingerprint. Any later revision
produces a new version, so an earlier confirmation can never authorize content
the user did not see.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from health_assistant.domain.constraints import ConstraintSet
from health_assistant.domain.errors import (
    ApprovalExpiredError,
    ApprovalPayloadChangedError,
    ApprovalRevokedError,
    ApprovalScopeError,
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


def fingerprint_items(items: Iterable[PlanItem]) -> str:
    """Return a stable SHA-256 digest over the user-visible content of ``items``.

    Ordering of items and of attribute tokens must not change the digest, so the
    same proposal always produces the same fingerprint on any machine.
    """
    payload = [
        {
            "item_id": item.item_id,
            "category": str(item.category),
            "title": item.title,
            "start": item.window.start.isoformat(),
            "end": item.window.end.isoformat(),
            "time_zone": item.window.time_zone,
            "attributes": sorted(item.attributes),
            "completion": str(item.completion),
        }
        for item in sorted(items, key=lambda item: item.item_id)
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Approval:
    """A confirmation that is valid only for one payload at one version."""

    approval_id: ApprovalId
    owner_id: UserId
    plan_id: PlanId
    plan_version: int
    scope: frozenset[PlanItemId]
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
            raise ValidationError("an approval must cover at least one plan item")
        if self.expires_at <= self.granted_at:
            raise ValidationError("approval expiry must follow the grant instant")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

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
    scope: frozenset[PlanItemId],
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
        raise ApprovalScopeError("approval scope must name at least one plan item")

    unknown = scope - plan.item_ids()
    if unknown:
        raise ApprovalScopeError(f"scope names items absent from this version: {sorted(unknown)}")

    scoped_items = tuple(item for item in plan.items if item.item_id in scope)
    reported = [item.item_id for item in scoped_items if item.is_reported]
    if reported:
        raise ApprovalScopeError(f"scope names items with reported outcomes: {sorted(reported)}")

    report = validate_plan(plan, constraints, at=now).for_items(scope)
    if report.is_blocking:
        details = "; ".join(
            f"{finding.item_id}: {finding.outcome} ({finding.detail})"
            for finding in report.blocking
        )
        raise PlanNotApprovableError(f"blocking constraint findings: {details}")

    if ttl <= timedelta(0):
        raise ValidationError("approval ttl must be positive")

    granted_at = require_utc(now, "now")
    return Approval(
        approval_id=approval_id,
        owner_id=plan.owner_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        scope=frozenset(scope),
        payload_fingerprint=fingerprint_items(scoped_items),
        granted_at=granted_at,
        expires_at=granted_at + ttl,
    )


def authorize_execution(
    approval: Approval,
    *,
    plan: PlanVersion,
    item_ids: frozenset[PlanItemId],
    actor_id: UserId,
    now: datetime,
) -> None:
    """Raise unless ``approval`` still authorizes acting on ``item_ids``.

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

    outside = item_ids - approval.scope
    if outside:
        raise ApprovalScopeError(f"items outside the approved scope: {sorted(outside)}")

    scoped_items = tuple(item for item in plan.items if item.item_id in approval.scope)
    if fingerprint_items(scoped_items) != approval.payload_fingerprint:
        raise ApprovalPayloadChangedError()


def validation_report_for(
    plan: PlanVersion, constraints: ConstraintSet, *, at: datetime
) -> ValidationReport:
    """Convenience wrapper so callers can preview findings before approving."""
    return validate_plan(plan, constraints, at=at)
