"""Plan persistence: lossless round trips, ownership, and version conflicts."""

import pytest
from sqlalchemy import Engine

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

pytestmark = pytest.mark.integration


def _register(engine: Engine, *users: UserId) -> None:
    with unit_of_work(engine) as work:
        for user in users:
            work.users.ensure(user_id=user, time_zone="America/Toronto", created_at=BASE_INSTANT)


def test_a_plan_version_round_trips_without_losing_detail(engine: Engine) -> None:
    _register(engine, OWNER)
    original = make_plan(
        make_item(
            "item-a",
            category=PlanItemCategory.NUTRITION,
            title="Sesame tofu bowl",
            attributes=("sesame", "rice"),
        ),
        make_item("item-b", start_hours=48, completion=CompletionStatus.COMPLETED),
    )

    with unit_of_work(engine) as work:
        work.plans.save(original)
    with unit_of_work(engine) as work:
        loaded = work.plans.get(owner_id=OWNER, plan_id=PLAN, version=1)

    assert loaded == original


def test_latest_returns_the_highest_version(engine: Engine) -> None:
    _register(engine, OWNER)
    first = make_plan(make_item("item-a"))
    second = revise(
        first,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(hours=1),
    )

    with unit_of_work(engine) as work:
        work.plans.save(first)
        work.plans.save(second)
    with unit_of_work(engine) as work:
        latest = work.plans.latest(owner_id=OWNER, plan_id=PLAN)

    assert latest is not None
    assert latest.version == 2
    assert latest.item(PlanItemId("item-a")).title == "Morning walk"


def test_another_user_reads_nothing(engine: Engine) -> None:
    _register(engine, OWNER, OTHER_USER)
    with unit_of_work(engine) as work:
        work.plans.save(make_plan(make_item("item-a")))

    with unit_of_work(engine) as work:
        assert work.plans.get(owner_id=OTHER_USER, plan_id=PLAN, version=1) is None
        assert work.plans.latest(owner_id=OTHER_USER, plan_id=PLAN) is None
        assert work.plans.latest(owner_id=OWNER, plan_id=PLAN) is not None


def test_writing_into_another_users_plan_is_refused(engine: Engine) -> None:
    _register(engine, OWNER, OTHER_USER)
    with unit_of_work(engine) as work:
        work.plans.save(make_plan(make_item("item-a")))

    intruder = make_plan(make_item("item-a"), owner=OTHER_USER)
    with pytest.raises(OwnershipError), unit_of_work(engine) as work:
        work.plans.save(intruder)


def test_two_revisions_of_one_base_cannot_both_be_stored(engine: Engine) -> None:
    """The lost-update case: both clients read version 1 and both write version 2."""
    _register(engine, OWNER)
    base = make_plan(make_item("item-a"))
    with unit_of_work(engine) as work:
        work.plans.save(base)

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

    with unit_of_work(engine) as work:
        work.plans.save(first)

    with pytest.raises(StalePlanRevisionError) as caught, unit_of_work(engine) as work:
        work.plans.save(second)
    assert caught.value.actual == 2

    with unit_of_work(engine) as work:
        latest = work.plans.latest(owner_id=OWNER, plan_id=PLAN)
    assert latest is not None
    assert latest.item(PlanItemId("item-a")).title == "Morning walk"


def test_a_failed_transaction_stores_nothing(engine: Engine) -> None:
    _register(engine, OWNER)
    failure = RuntimeError("interrupted midway")

    with pytest.raises(RuntimeError), unit_of_work(engine) as work:
        work.plans.save(make_plan(make_item("item-a")))
        raise failure

    with unit_of_work(engine) as work:
        assert work.plans.latest(owner_id=OWNER, plan_id=PLAN) is None
