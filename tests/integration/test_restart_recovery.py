"""What survives a worker that stops existing mid-flight.

These tests kill a real process rather than advancing a clock, because the
question is what the database is left holding when a worker never comes back.
"""

import asyncio
import os
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.application.worker import (
    claim_next_operation,
    release_expired_leases,
)
from health_assistant.domain.identifiers import OperationId, PlanId
from health_assistant.domain.operations import OperationState, ProviderOutcome, reconcile
from tests.integration.conftest import REPOSITORY_ROOT
from tests.integration.crash_worker import CRASH_EXIT_CODE, LEASE, WORKER_ID
from tests.integration.support import build_approval, register_users, seed_queued_operation
from tests.support import OWNER, PLAN, at, make_item, make_plan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _crash_a_worker(database_url: str, mode: str) -> None:
    """Run a worker that claims one operation and then dies in the given way."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.integration.crash_worker",
        database_url,
        mode,
        cwd=str(REPOSITORY_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == CRASH_EXIT_CODE, stderr.decode()


async def test_a_worker_that_dies_after_committing_leaves_recoverable_work(
    engine: AsyncEngine, database_url: str
) -> None:
    await seed_queued_operation(engine)

    await _crash_a_worker(database_url, "commit")

    async with unit_of_work(engine) as work:
        stranded = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert stranded is not None
    assert stranded.state is OperationState.EXECUTING
    assert stranded.lease is not None
    assert stranded.lease.worker_id == WORKER_ID

    # Nobody else may take it while the dead worker's lease is still live.
    async with unit_of_work(engine) as work:
        assert await work.operations.claim_next() is None

    async with unit_of_work(engine) as work:
        released = await release_expired_leases(work, now=at(minutes=3) + LEASE + LEASE)
    assert [item.state for item in released] == [OperationState.OUTCOME_UNKNOWN]
    assert released[0].attempts == 1, "recovery must not consume another attempt"

    # Recovery ends at a verified outcome, not a guess.
    async with unit_of_work(engine) as work:
        unknown = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
        assert unknown is not None
        settled = reconcile(
            unknown,
            outcome=ProviderOutcome(applied=True, external_ref="evt-synthetic-1"),
            now=at(minutes=20),
        )
        await work.operations.advance(settled, previous=unknown)

    async with unit_of_work(engine) as work:
        final = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert final is not None
    assert final.state is OperationState.SUCCEEDED
    assert final.external_ref == "evt-synthetic-1"


async def test_a_worker_that_dies_before_committing_leaves_no_trace(
    engine: AsyncEngine, database_url: str
) -> None:
    await seed_queued_operation(engine)

    await _crash_a_worker(database_url, "rollback")

    async with unit_of_work(engine) as work:
        untouched = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert untouched is not None
    assert untouched.state is OperationState.QUEUED
    assert untouched.lease is None
    assert untouched.attempts == 0

    # A healthy worker takes it immediately, with no waiting on a lease.
    async with unit_of_work(engine) as work:
        outcome = await claim_next_operation(
            work, worker_id="worker-2", now=at(minutes=4), lease_duration=LEASE
        )
    assert outcome.claimed is not None
    assert outcome.claimed.attempts == 1


async def test_a_failed_transaction_leaves_neither_approval_nor_operation(
    engine: AsyncEngine,
) -> None:
    """The unit of work is the boundary: a partial write is not a possible state."""
    await register_users(engine, OWNER)
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = build_approval(plan)

    with pytest.raises(RuntimeError):
        async with unit_of_work(engine) as work:
            await work.plans.save(plan)
            await work.approvals.save(approval)
            raise RuntimeError("interrupted between related writes")

    async with unit_of_work(engine) as work:
        assert await work.plans.latest(owner_id=OWNER, plan_id=PlanId(PLAN)) is None
        assert await work.approvals.get(owner_id=OWNER, approval_id=approval.approval_id) is None
