"""Shared setup for the database-backed tests."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.domain.actions import OperationKind
from health_assistant.domain.approvals import Approval, grant_approval
from health_assistant.domain.identifiers import ApprovalId, OperationId, PlanItemId, UserId
from health_assistant.domain.operations import (
    ToolOperation,
    confirm,
    propose,
    request_confirmation,
)
from health_assistant.domain.plans import PlanVersion
from tests.support import (
    BASE_INSTANT,
    EMPTY_CONSTRAINTS,
    OWNER,
    at,
    make_item,
    make_plan,
    make_scope,
)

ITEM = PlanItemId("item-a")
APPROVAL_TTL = timedelta(minutes=30)


async def register_users(engine: AsyncEngine, *users: UserId) -> None:
    async with unit_of_work(engine) as work:
        for user in users:
            await work.users.ensure(
                user_id=user, time_zone="America/Toronto", created_at=BASE_INSTANT
            )


def build_approval(
    plan: PlanVersion,
    *,
    approval_id: str = "approval-1",
    ttl: timedelta = APPROVAL_TTL,
) -> Approval:
    return grant_approval(
        approval_id=ApprovalId(approval_id),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=make_scope("item-a"),
        actor_id=plan.owner_id,
        now=at(),
        ttl=ttl,
    )


def build_queued_operation(
    plan: PlanVersion, approval: Approval, *, operation_id: str = "op-1"
) -> ToolOperation:
    proposed = propose(
        operation_id=OperationId(operation_id),
        plan=plan,
        item_id=ITEM,
        kind=OperationKind.CREATE_EVENT,
        now=at(),
    )
    return confirm(
        request_confirmation(proposed, now=at(minutes=1)),
        approval=approval,
        plan=plan,
        actor_id=OWNER,
        now=at(minutes=2),
    )


async def seed_queued_operation(
    engine: AsyncEngine,
    *,
    approval_ttl: timedelta = APPROVAL_TTL,
    operation_id: str = "op-1",
) -> tuple[PlanVersion, Approval, ToolOperation]:
    """Persist a user, a plan, an approval, and one queued operation."""
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = build_approval(plan, ttl=approval_ttl)
    operation = build_queued_operation(plan, approval, operation_id=operation_id)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
        await work.operations.save(operation)
    return plan, approval, operation
