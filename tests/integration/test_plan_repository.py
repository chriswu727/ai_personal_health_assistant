"""Plan persistence: lossless round trips, ownership, and version conflicts."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.domain.errors import OwnershipError, StalePlanRevisionError
from health_assistant.domain.identifiers import PlanItemId, UserId
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItemCategory,
    ReplaceItem,
    revise,
)
from tests.support import BASE_INSTANT, OTHER_USER, OWNER, PLAN, at, make_item, make_plan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _register(engine: AsyncEngine, *users: UserId) -> None:
    async with unit_of_work(engine) as work:
        for user in users:
            await work.users.ensure(
                user_id=user, time_zone="America/Toronto", created_at=BASE_INSTANT
            )


async def test_a_plan_version_round_trips_without_losing_detail(engine: AsyncEngine) -> None:
    await _register(engine, OWNER)
    original = make_plan(
        make_item(
            "item-a",
            category=PlanItemCategory.NUTRITION,
            title="Sesame tofu bowl",
            attributes=("sesame", "rice"),
        ),
        make_item("item-b", start_hours=48, completion=CompletionStatus.COMPLETED),
    )

    async with unit_of_work(engine) as work:
        await work.plans.save(original)
    async with unit_of_work(engine) as work:
        loaded = await work.plans.get(owner_id=OWNER, plan_id=PLAN, version=1)

    assert loaded == original


async def test_latest_returns_the_highest_version(engine: AsyncEngine) -> None:
    await _register(engine, OWNER)
    first = make_plan(make_item("item-a"))
    second = revise(
        first,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(hours=1),
    )

    async with unit_of_work(engine) as work:
        await work.plans.save(first)
        await work.plans.save(second)
    async with unit_of_work(engine) as work:
        latest = await work.plans.latest(owner_id=OWNER, plan_id=PLAN)

    assert latest is not None
    assert latest.version == 2
    assert latest.item(PlanItemId("item-a")).title == "Morning walk"


async def test_another_user_reads_nothing(engine: AsyncEngine) -> None:
    await _register(engine, OWNER, OTHER_USER)
    async with unit_of_work(engine) as work:
        await work.plans.save(make_plan(make_item("item-a")))

    async with unit_of_work(engine) as work:
        assert await work.plans.get(owner_id=OTHER_USER, plan_id=PLAN, version=1) is None
        assert await work.plans.latest(owner_id=OTHER_USER, plan_id=PLAN) is None
        assert await work.plans.latest(owner_id=OWNER, plan_id=PLAN) is not None


async def test_writing_into_another_users_plan_is_refused(engine: AsyncEngine) -> None:
    await _register(engine, OWNER, OTHER_USER)
    async with unit_of_work(engine) as work:
        await work.plans.save(make_plan(make_item("item-a")))

    intruder = make_plan(make_item("item-a"), owner=OTHER_USER)
    with pytest.raises(OwnershipError):
        async with unit_of_work(engine) as work:
            await work.plans.save(intruder)


async def test_two_revisions_of_one_base_cannot_both_be_stored(engine: AsyncEngine) -> None:
    """The lost-update case: both clients read version 1 and both write version 2."""
    await _register(engine, OWNER)
    base = make_plan(make_item("item-a"))
    async with unit_of_work(engine) as work:
        await work.plans.save(base)

    first = revise(
        base,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(hours=1),
    )
    second = revise(
        base,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Evening swim"))],
        now=at(hours=2),
    )

    async with unit_of_work(engine) as work:
        await work.plans.save(first)

    with pytest.raises(StalePlanRevisionError) as caught:
        async with unit_of_work(engine) as work:
            await work.plans.save(second)
    assert caught.value.actual == 2

    async with unit_of_work(engine) as work:
        latest = await work.plans.latest(owner_id=OWNER, plan_id=PLAN)
    assert latest is not None
    assert latest.item(PlanItemId("item-a")).title == "Morning walk"


async def test_a_failed_transaction_stores_nothing(engine: AsyncEngine) -> None:
    await _register(engine, OWNER)
    failure = RuntimeError("interrupted midway")

    with pytest.raises(RuntimeError):
        async with unit_of_work(engine) as work:
            await work.plans.save(make_plan(make_item("item-a")))
            raise failure

    async with unit_of_work(engine) as work:
        assert await work.plans.latest(owner_id=OWNER, plan_id=PLAN) is None
