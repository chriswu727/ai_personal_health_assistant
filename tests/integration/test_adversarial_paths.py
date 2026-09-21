"""Attempts to reach a protected state by a path nobody designed.

The Sprint 1 retrospective recorded why these exist: the defects that shipped
lived between entry points, not inside them, and a suite that mirrors the shape
of the code never crosses that boundary. Each test here takes a route the
application would not take and asserts it is refused anyway.
"""

from dataclasses import replace

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.adapters.persistence.schema import approvals, tool_operations
from health_assistant.domain.errors import InvalidTransitionError, OwnershipError
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
from tests.support import BASE_INSTANT, OTHER_USER, OWNER, PLAN, at, make_item, make_plan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def violated_constraint(error: IntegrityError) -> str:
    """Return the constraint the server named, so a probe cannot pass by accident."""
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return str(name) if name is not None else ""


async def test_execution_cannot_skip_confirmation(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = build_approval(plan)
    queued = build_queued_operation(plan, approval)
    awaiting = replace(queued, state=OperationState.AWAITING_CONFIRMATION)

    async with unit_of_work(engine) as work:
        await work.plans.save(plan)
        await work.approvals.save(approval)
        await work.operations.add(awaiting)

    forged = replace(awaiting, state=OperationState.EXECUTING, attempts=1)
    with pytest.raises(InvalidTransitionError):
        async with unit_of_work(engine) as work:
            await work.operations.advance(forged, previous=awaiting)


async def test_success_cannot_be_written_without_executing(engine: AsyncEngine) -> None:
    _, _, queued = await seed_queued_operation(engine)
    forged = replace(queued, state=OperationState.SUCCEEDED, external_ref="evt-never-attempted")

    with pytest.raises(InvalidTransitionError):
        async with unit_of_work(engine) as work:
            await work.operations.advance(forged, previous=queued)


async def test_an_unknown_outcome_cannot_be_requeued_through_storage(
    engine: AsyncEngine,
) -> None:
    """The reconciliation requirement must not be escapable by writing state directly."""
    plan, approval, queued = await seed_queued_operation(engine)
    executing = claim(
        queued,
        approval=approval,
        plan=plan,
        worker_id="worker-1",
        now=at(minutes=3),
        lease_duration=BASE_INSTANT - BASE_INSTANT + (at(minutes=8) - at(minutes=3)),
    )
    unknown = record_ambiguous_outcome(executing, reason="timeout", now=at(minutes=4))
    async with unit_of_work(engine) as work:
        await work.operations.advance(executing, previous=queued)
        await work.operations.advance(unknown, previous=executing)

    forged = replace(unknown, state=OperationState.QUEUED, lease=None)
    with pytest.raises(InvalidTransitionError):
        async with unit_of_work(engine) as work:
            await work.operations.advance(forged, previous=unknown)


async def test_a_cancelled_operation_cannot_be_revived(engine: AsyncEngine) -> None:
    _, _, queued = await seed_queued_operation(engine)
    cancelled = replace(queued, state=OperationState.CANCELLED, updated_at=at(minutes=3))
    async with unit_of_work(engine) as work:
        await work.operations.advance(cancelled, previous=queued)

    forged = replace(cancelled, state=OperationState.QUEUED, updated_at=at(minutes=4))
    with pytest.raises(InvalidTransitionError):
        async with unit_of_work(engine) as work:
            await work.operations.advance(forged, previous=cancelled)


async def test_the_database_refuses_execution_without_a_recorded_approval(
    engine: AsyncEngine,
) -> None:
    """Written through the connection, so it holds even if no repository is involved."""
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"))
    async with unit_of_work(engine) as work:
        await work.plans.save(plan)

    with pytest.raises(IntegrityError) as caught:
        async with unit_of_work(engine) as work:
            await work.connection.execute(
                insert(tool_operations).values(
                    operation_id="op-forged",
                    owner_id=OWNER,
                    plan_id=PLAN,
                    plan_version=1,
                    item_id="item-a",
                    kind="create_event",
                    idempotency_key="forged-key",
                    state="executing",
                    approval_id=None,
                    attempts=1,
                    retry_budget=3,
                    created_at=BASE_INSTANT,
                    updated_at=BASE_INSTANT,
                )
            )

    assert violated_constraint(caught.value) == "ck_tool_operations_approved_before_execution"


async def test_an_approval_cannot_reference_another_users_plan(
    engine: AsyncEngine,
) -> None:
    await register_users(engine, OWNER, OTHER_USER)
    plan = make_plan(make_item("item-a"))
    async with unit_of_work(engine) as work:
        await work.plans.save(plan)

    with pytest.raises(IntegrityError) as caught:
        async with unit_of_work(engine) as work:
            await work.connection.execute(
                insert(approvals).values(
                    approval_id="approval-forged",
                    owner_id=OTHER_USER,
                    plan_id=PLAN,
                    plan_version=1,
                    payload_fingerprint="whatever",
                    granted_at=BASE_INSTANT,
                    expires_at=at(minutes=30),
                )
            )

    assert violated_constraint(caught.value) == "fk_approvals_plan_version"


async def test_an_operation_cannot_reference_another_users_plan(
    engine: AsyncEngine,
) -> None:
    await register_users(engine, OWNER, OTHER_USER)
    plan = make_plan(make_item("item-a"))
    async with unit_of_work(engine) as work:
        await work.plans.save(plan)

    with pytest.raises(IntegrityError) as caught:
        async with unit_of_work(engine) as work:
            await work.connection.execute(
                insert(tool_operations).values(
                    operation_id="op-forged",
                    owner_id=OTHER_USER,
                    plan_id=PLAN,
                    plan_version=1,
                    item_id="item-a",
                    kind="create_event",
                    idempotency_key="forged-key",
                    state="proposed",
                    attempts=0,
                    retry_budget=3,
                    created_at=BASE_INSTANT,
                    updated_at=BASE_INSTANT,
                )
            )

    assert violated_constraint(caught.value) == "fk_tool_operations_plan_version"


async def test_another_user_cannot_advance_an_operation(engine: AsyncEngine) -> None:
    await register_users(engine, OTHER_USER)
    _, _, queued = await seed_queued_operation(engine)

    with pytest.raises(OwnershipError):
        async with unit_of_work(engine) as work:
            await work.operations.advance(
                replace(queued, owner_id=OTHER_USER, updated_at=at(minutes=3)),
                previous=queued,
            )
