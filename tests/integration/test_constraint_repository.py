"""Constraint persistence: round trips, expiry filtering, and owner isolation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.domain.constraints import ConstraintKind, ConstraintSource
from health_assistant.domain.errors import OwnershipError
from tests.integration.support import register_users
from tests.support import (
    OTHER_USER,
    OWNER,
    at,
    make_constraint,
    window,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_a_token_constraint_round_trips(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    original = make_constraint("c-allergy", subject="peanut butter")

    async with unit_of_work(engine) as work:
        await work.constraints.save(original)
    async with unit_of_work(engine) as work:
        stored = await work.constraints.all_for(OWNER)

    assert stored.constraints == (original,)


async def test_a_window_constraint_round_trips_with_its_zone(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    original = make_constraint(
        "c-busy",
        kind=ConstraintKind.UNAVAILABLE_WINDOW,
        window_override=window(start_hours=72, duration_hours=3),
    )

    async with unit_of_work(engine) as work:
        await work.constraints.save(original)
    async with unit_of_work(engine) as work:
        stored = await work.constraints.all_for(OWNER)

    assert stored.constraints == (original,)
    assert stored.constraints[0].window is not None
    assert stored.constraints[0].window.time_zone == "America/Toronto"


async def test_saving_again_replaces_the_stored_constraint(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    async with unit_of_work(engine) as work:
        await work.constraints.save(make_constraint("c-1", subject="peanut"))
        await work.constraints.save(
            make_constraint("c-1", subject="peanut", source=ConstraintSource.INFERRED)
        )
    async with unit_of_work(engine) as work:
        stored = await work.constraints.all_for(OWNER)

    assert len(stored) == 1
    assert not stored.constraints[0].is_confirmed


async def test_expired_constraints_are_excluded(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER)
    async with unit_of_work(engine) as work:
        await work.constraints.save(make_constraint("c-live", subject="peanut"))
        await work.constraints.save(
            make_constraint("c-expiring", subject="shellfish", expires_at=at(hours=1))
        )

    async with unit_of_work(engine) as work:
        before = await work.constraints.active_at(OWNER, at())
        after = await work.constraints.active_at(OWNER, at(hours=2))
        everything = await work.constraints.all_for(OWNER)

    assert len(before) == 2
    assert [c.constraint_id for c in after] == ["c-live"]
    assert len(everything) == 2


async def test_another_user_neither_reads_nor_overwrites(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER, OTHER_USER)
    async with unit_of_work(engine) as work:
        await work.constraints.save(make_constraint("c-1", subject="peanut"))

    async with unit_of_work(engine) as work:
        assert len(await work.constraints.all_for(OTHER_USER)) == 0

    intruder = make_constraint("c-1", subject="nothing", owner=OTHER_USER)
    with pytest.raises(OwnershipError):
        async with unit_of_work(engine) as work:
            await work.constraints.save(intruder)

    async with unit_of_work(engine) as work:
        stored = await work.constraints.all_for(OWNER)
    assert stored.constraints[0].subject == "peanut"
