"""A stored approval must authorize exactly what the in-memory one did."""

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.domain.actions import OperationKind
from health_assistant.domain.approvals import authorize_execution, grant_approval
from health_assistant.domain.errors import (
    ApprovalActionNotAuthorizedError,
    ApprovalRevokedError,
    ApprovalTargetMismatchError,
    OwnershipError,
)
from health_assistant.domain.identifiers import ApprovalId
from tests.integration.support import APPROVAL_TTL, build_approval, register_users
from tests.support import (
    EMPTY_CONSTRAINTS,
    OTHER_USER,
    OWNER,
    at,
    make_item,
    make_plan,
    make_scope,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_an_approval_round_trips_with_its_scope(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    approval = build_approval(plan)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-1"))

    assert stored == approval


async def test_a_stored_approval_authorizes_exactly_what_it_did_in_memory(
    engine: AsyncEngine,
) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    approval = build_approval(plan)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-1"))
    assert stored is not None

    authorize_execution(
        stored,
        plan=plan,
        actions=make_scope("item-a"),
        actor_id=OWNER,
        now=at(minutes=5),
    )
    with pytest.raises(ApprovalActionNotAuthorizedError):
        authorize_execution(
            stored,
            plan=plan,
            actions=make_scope("item-a", kind=OperationKind.CANCEL_EVENT),
            actor_id=OWNER,
            now=at(minutes=5),
        )


async def test_a_compensation_target_survives_storage(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    approval = grant_approval(
        approval_id=ApprovalId("approval-cancel"),
        plan=plan,
        constraints=EMPTY_CONSTRAINTS,
        scope=make_scope("item-a", kind=OperationKind.CANCEL_EVENT, compensates="write-a"),
        actor_id=OWNER,
        now=at(),
        ttl=APPROVAL_TTL,
    )

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-cancel"))
    assert stored is not None
    assert stored == approval

    with pytest.raises(ApprovalTargetMismatchError):
        authorize_execution(
            stored,
            plan=plan,
            actions=make_scope("item-a", kind=OperationKind.CANCEL_EVENT, compensates="write-b"),
            actor_id=OWNER,
            now=at(minutes=5),
        )


async def test_revocation_is_persisted(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    approval = build_approval(plan)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
    async with unit_of_work(engine) as work:
        await work.approvals.save(approval.revoke(at=at(minutes=3)))
    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-1"))

    assert stored is not None
    assert stored.is_revoked
    with pytest.raises(ApprovalRevokedError):
        authorize_execution(
            stored,
            plan=plan,
            actions=make_scope("item-a"),
            actor_id=OWNER,
            now=at(minutes=5),
        )


async def test_another_user_neither_reads_nor_revokes(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER, OTHER_USER)
    plan = make_plan(make_item("item-a"))
    approval = build_approval(plan)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)

    async with unit_of_work(engine) as work:
        assert (
            await work.approvals.get(owner_id=OTHER_USER, approval_id=ApprovalId("approval-1"))
            is None
        )

    with pytest.raises(OwnershipError):
        async with unit_of_work(engine) as work:
            await work.approvals.save(
                replace(approval, owner_id=OTHER_USER, revoked_at=at(minutes=3))
            )

    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-1"))
    assert stored is not None
    assert not stored.is_revoked


async def test_a_stale_snapshot_cannot_undo_a_revocation(engine: AsyncEngine) -> None:
    """Regression: a delayed write is enough; no forged approval is needed."""
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    approval = build_approval(plan)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
    async with unit_of_work(engine) as work:
        await work.approvals.save(approval.revoke(at=at(minutes=2.5)))

    # The caller still holds the pre-revocation object and saves it again.
    async with unit_of_work(engine) as work:
        await work.approvals.save(approval)

    async with unit_of_work(engine) as work:
        stored = await work.approvals.get(owner_id=OWNER, approval_id=ApprovalId("approval-1"))
    assert stored is not None
    assert stored.is_revoked
    with pytest.raises(ApprovalRevokedError):
        authorize_execution(
            stored,
            plan=plan,
            actions=make_scope("item-a"),
            actor_id=OWNER,
            now=at(minutes=5),
        )
