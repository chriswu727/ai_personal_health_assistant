"""The worker's use cases against real storage."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.application.worker import (
    claim_next_operation,
    release_expired_leases,
)
from health_assistant.domain.identifiers import OperationId
from health_assistant.domain.operations import OperationState, claim
from tests.integration.support import seed_queued_operation
from tests.support import OWNER, at

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LEASE = timedelta(minutes=5)


async def test_an_authorized_operation_is_claimed_and_leased(engine: AsyncEngine) -> None:
    await seed_queued_operation(engine)

    async with unit_of_work(engine) as work:
        outcome = await claim_next_operation(
            work, worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
        )

    assert outcome.claimed is not None
    assert outcome.claimed.state is OperationState.EXECUTING
    assert outcome.claimed.lease is not None
    assert outcome.claimed.lease.worker_id == "worker-1"

    async with unit_of_work(engine) as work:
        stored = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert stored == outcome.claimed


async def test_an_empty_queue_reports_idle(engine: AsyncEngine) -> None:
    async with unit_of_work(engine) as work:
        outcome = await claim_next_operation(
            work, worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
        )

    assert outcome.is_idle


async def test_a_confirmation_that_lapsed_before_a_worker_arrived_is_cancelled(
    engine: AsyncEngine,
) -> None:
    """Waiting never makes an expired confirmation valid, so it must not spin."""
    await seed_queued_operation(engine, approval_ttl=timedelta(minutes=5))

    async with unit_of_work(engine) as work:
        outcome = await claim_next_operation(
            work, worker_id="worker-1", now=at(minutes=10), lease_duration=LEASE
        )

    assert outcome.claimed is None
    assert outcome.cancelled is not None
    assert outcome.cancelled.state is OperationState.CANCELLED
    assert "expired" in (outcome.cancelled.last_error or "")

    async with unit_of_work(engine) as work:
        assert await work.operations.claim_next() is None


async def test_a_revoked_confirmation_stops_the_work(engine: AsyncEngine) -> None:
    _, approval, _ = await seed_queued_operation(engine)
    async with unit_of_work(engine) as work:
        await work.approvals.save(approval.revoke(at=at(minutes=2.5)))

    async with unit_of_work(engine) as work:
        outcome = await claim_next_operation(
            work, worker_id="worker-1", now=at(minutes=3), lease_duration=LEASE
        )

    assert outcome.cancelled is not None
    assert "revoked" in (outcome.cancelled.last_error or "")


async def test_an_expired_lease_returns_work_for_reconciliation(
    engine: AsyncEngine,
) -> None:
    """Not failed: the external write may well have landed."""
    plan, approval, operation = await seed_queued_operation(engine)
    async with unit_of_work(engine) as work:
        await work.operations.save(
            claim(
                operation,
                approval=approval,
                plan=plan,
                worker_id="worker-1",
                now=at(minutes=3),
                lease_duration=LEASE,
            )
        )

    async with unit_of_work(engine) as work:
        released = await release_expired_leases(work, now=at(minutes=9))

    assert [item.state for item in released] == [OperationState.OUTCOME_UNKNOWN]
    assert released[0].lease is None

    async with unit_of_work(engine) as work:
        stored = await work.operations.get(owner_id=OWNER, operation_id=OperationId("op-1"))
    assert stored is not None
    assert stored.state is OperationState.OUTCOME_UNKNOWN
    assert stored.attempts == 1, "reconciliation must not consume another attempt"
