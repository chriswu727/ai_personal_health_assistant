"""Durable operations: claiming, lease expiry, and the deduplication key."""

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.identifiers import OperationId
from health_assistant.domain.operations import (
    OperationState,
    claim,
    record_ambiguous_outcome,
)
from tests.integration.support import (
    build_approval,
    build_queued_operation,
    register_users,
    seed_queued_operation,
)
from tests.support import OTHER_USER, OWNER, at, make_item, make_plan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LEASE = timedelta(minutes=5)


async def test_an_operation_round_trips_through_its_lifecycle(engine: AsyncEngine) -> None:
    plan, approval, operation = await seed_queued_operation(engine)

    async with unit_of_work(engine) as work:
        stored = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert stored == operation

    executing = claim(
        operation,
        approval=approval,
        plan=plan,
        worker_id="worker-1",
        now=at(minutes=3),
        lease_duration=LEASE,
    )
    unknown = record_ambiguous_outcome(executing, reason="timeout", now=at(minutes=4))
    async with unit_of_work(engine) as work:
        await work.operations.save(executing)
        await work.operations.save(unknown)

    async with unit_of_work(engine) as work:
        reloaded = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert reloaded == unknown
    assert reloaded is not None
    assert reloaded.last_error == "timeout"
    assert reloaded.attempts == 1


async def test_another_user_neither_reads_nor_advances(engine: AsyncEngine) -> None:
    await register_users(engine, OTHER_USER)
    _, _, operation = await seed_queued_operation(engine)

    async with unit_of_work(engine) as work:
        assert (
            await work.operations.get(owner_id=OTHER_USER, operation_id=OperationId("op-1")) is None
        )

    with pytest.raises(OwnershipError):
        async with unit_of_work(engine) as work:
            await work.operations.save(replace(operation, owner_id=OTHER_USER))


async def test_two_operations_cannot_share_an_idempotency_key(
    engine: AsyncEngine,
) -> None:
    """A duplicate key would defeat the provider's own deduplication."""
    _, _, operation = await seed_queued_operation(engine)

    with pytest.raises(IntegrityError):
        async with unit_of_work(engine) as work:
            await work.operations.save(replace(operation, operation_id=OperationId("op-copy")))


async def test_claiming_returns_the_oldest_queued_operation(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = build_approval(plan)
    first = build_queued_operation(plan, approval, operation_id="op-early")
    later = replace(
        build_queued_operation(plan, approval, operation_id="op-late"),
        created_at=at(hours=1),
    )

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
        await work.operations.save(later)
        await work.operations.save(first)

    async with unit_of_work(engine) as work:
        candidate = await work.operations.claim_next()

    assert candidate is not None
    assert candidate.operation_id == "op-early"


async def test_two_workers_do_not_claim_the_same_operation(engine: AsyncEngine) -> None:
    """SKIP LOCKED: the second worker passes over the locked row rather than waiting."""
    await seed_queued_operation(engine)

    async with unit_of_work(engine) as first, unit_of_work(engine) as second:
        taken = await first.operations.claim_next()
        passed_over = await second.operations.claim_next()

    assert taken is not None
    assert passed_over is None


async def test_expired_leases_are_reported_and_live_ones_are_not(
    engine: AsyncEngine,
) -> None:
    plan, approval, operation = await seed_queued_operation(engine)
    executing = claim(
        operation,
        approval=approval,
        plan=plan,
        worker_id="worker-1",
        now=at(minutes=3),
        lease_duration=LEASE,
    )
    async with unit_of_work(engine) as work:
        await work.operations.save(executing)

    async with unit_of_work(engine) as work:
        assert await work.operations.expired_leases(now=at(minutes=4)) == ()
    async with unit_of_work(engine) as work:
        overdue = await work.operations.expired_leases(now=at(minutes=9))

    assert [item.operation_id for item in overdue] == ["op-1"]
    assert overdue[0].state is OperationState.EXECUTING
