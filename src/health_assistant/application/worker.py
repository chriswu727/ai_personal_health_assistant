"""The worker's use cases: taking authorized work and releasing dead leases.

Claiming is two decisions, not one. The store picks a row nobody else holds; the
domain decides whether that row may still be executed. Keeping them apart means
the authorization check at the execution boundary is the same code the
confirmation path uses, rather than a second implementation in a query.

That check is only worth anything against current records. The plan is loaded at
its newest version, not at the version the operation was queued under, because a
revision the user made while the work waited is exactly what should invalidate
the confirmation. Both the plan and the approval are read so that a concurrent
revision or revocation orders itself against the claim rather than slipping
between the read and the commit.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from health_assistant.application.ports import UnitOfWork
from health_assistant.domain.errors import ApprovalError, OperationIdentityError
from health_assistant.domain.operations import ToolOperation, cancel, claim, expire_lease


@dataclass(frozen=True, slots=True)
class ClaimOutcome:
    """What a claim attempt produced.

    A cancelled operation is reported rather than swallowed: the queue was not
    empty, and the caller should not read ``None`` as "nothing to do".
    """

    claimed: ToolOperation | None = None
    cancelled: ToolOperation | None = None

    @property
    def is_idle(self) -> bool:
        return self.claimed is None and self.cancelled is None


async def claim_next_operation(
    work: UnitOfWork,
    *,
    worker_id: str,
    now: datetime,
    lease_duration: timedelta,
) -> ClaimOutcome:
    """Take the next queued operation, if it is still authorized.

    An operation whose authorization has lapsed is cancelled rather than left in
    the queue. Leaving it would spin: nothing about waiting makes an expired
    confirmation valid again, and the user must confirm afresh.
    """
    candidate = await work.operations.claim_next()
    if candidate is None:
        return ClaimOutcome()

    plan = await work.plans.latest(
        owner_id=candidate.owner_id, plan_id=candidate.plan_id, for_update=True
    )
    approval = (
        None
        if candidate.approval_id is None
        else await work.approvals.get(
            owner_id=candidate.owner_id,
            approval_id=candidate.approval_id,
            for_update=True,
        )
    )
    if plan is None or approval is None:
        return await _cancel(
            work, candidate, now=now, reason="the authorizing plan or approval is missing"
        )

    try:
        claimed = claim(
            candidate,
            approval=approval,
            plan=plan,
            worker_id=worker_id,
            now=now,
            lease_duration=lease_duration,
        )
    except (ApprovalError, OperationIdentityError) as lapsed:
        return await _cancel(work, candidate, now=now, reason=str(lapsed))

    await work.operations.advance(claimed, previous=candidate)
    return ClaimOutcome(claimed=claimed)


async def release_expired_leases(
    work: UnitOfWork, *, now: datetime, limit: int = 50
) -> tuple[ToolOperation, ...]:
    """Move operations whose worker stopped reporting to an unknown outcome.

    Not to failed: the external write may well have landed, and only
    reconciliation against the provider can say.
    """
    released = []
    for operation in await work.operations.expired_leases(now=now, limit=limit):
        moved = expire_lease(operation, now=now)
        await work.operations.advance(moved, previous=operation)
        released.append(moved)
    return tuple(released)


async def _cancel(
    work: UnitOfWork, operation: ToolOperation, *, now: datetime, reason: str
) -> ClaimOutcome:
    cancelled = cancel(operation, now=now, reason=reason)
    await work.operations.advance(cancelled, previous=operation)
    return ClaimOutcome(cancelled=cancelled)
