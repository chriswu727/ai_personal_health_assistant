"""Plan revision rules: ownership, concurrency, and immutable history."""

import pytest

from health_assistant.domain.errors import (
    CompletedHistoryError,
    DuplicatePlanItemError,
    EmptyRevisionError,
    OwnershipError,
    StalePlanRevisionError,
    UnknownPlanItemError,
    ValidationError,
)
from health_assistant.domain.identifiers import PlanItemId
from health_assistant.domain.plans import (
    AddItem,
    CompletionStatus,
    RecordCompletion,
    RemoveItem,
    ReplaceItem,
    revise,
)
from tests.support import BASE_INSTANT, OTHER_USER, OWNER, at, make_item, make_plan


def test_initial_version_has_no_parent() -> None:
    plan = make_plan(make_item("item-a"))
    assert plan.version == 1
    assert plan.parent_version is None


def test_items_are_stored_in_a_canonical_order() -> None:
    later = make_item("item-b", start_hours=48)
    earlier = make_item("item-a", start_hours=24)
    plan = make_plan(later, earlier)

    assert [item.item_id for item in plan.items] == ["item-a", "item-b"]


def test_revision_increments_the_version_and_records_the_parent() -> None:
    plan = make_plan(make_item("item-a"))
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[AddItem(make_item("item-b", start_hours=48))],
        now=at(hours=1),
    )

    assert revised.version == 2
    assert revised.parent_version == 1
    assert plan.version == 1, "the base version must not be mutated"


def test_revision_leaves_untouched_items_identical() -> None:
    untouched = make_item("item-b", title="Meal prep", start_hours=48)
    plan = make_plan(make_item("item-a"), untouched)
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(hours=1),
    )

    assert revised.item(PlanItemId("item-b")) == untouched
    assert revised.item(PlanItemId("item-a")).title == "Morning walk"


def test_a_stale_expected_version_is_rejected() -> None:
    plan = make_plan(make_item("item-a"))
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(hours=1),
    )

    with pytest.raises(StalePlanRevisionError) as caught:
        revise(
            revised,
            actor_id=OWNER,
            expected_version=1,
            changes=[RemoveItem(PlanItemId("item-a"))],
            now=at(hours=2),
        )
    assert caught.value.actual == 2


def test_another_user_may_not_revise_the_plan() -> None:
    plan = make_plan(make_item("item-a"))
    with pytest.raises(OwnershipError):
        revise(
            plan,
            actor_id=OTHER_USER,
            expected_version=1,
            changes=[RemoveItem(PlanItemId("item-a"))],
            now=at(hours=1),
        )


def test_reported_items_cannot_be_replaced_or_removed() -> None:
    completed = make_item("item-a", completion=CompletionStatus.COMPLETED)
    plan = make_plan(completed, make_item("item-b", start_hours=48))

    with pytest.raises(CompletedHistoryError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[ReplaceItem(make_item("item-a", title="Rewritten"))],
            now=at(hours=1),
        )
    with pytest.raises(CompletedHistoryError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[RemoveItem(PlanItemId("item-a"))],
            now=at(hours=1),
        )


def test_editing_one_item_preserves_completed_history() -> None:
    completed = make_item("item-a", completion=CompletionStatus.COMPLETED)
    plan = make_plan(completed, make_item("item-b", start_hours=48))
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-b", title="Longer walk", start_hours=48))],
        now=at(hours=1),
    )

    assert revised.item(PlanItemId("item-a")) == completed
    assert len(revised.proposed_items()) == 1


def test_a_missing_record_is_unreported_rather_than_skipped() -> None:
    plan = make_plan(make_item("item-a"))
    assert plan.item(PlanItemId("item-a")).completion is CompletionStatus.UNREPORTED
    assert not plan.item(PlanItemId("item-a")).is_reported


def test_completion_is_recorded_once_and_not_rewritten() -> None:
    plan = make_plan(make_item("item-a"))
    reported = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[RecordCompletion(PlanItemId("item-a"), CompletionStatus.SKIPPED)],
        now=at(hours=1),
    )

    assert reported.item(PlanItemId("item-a")).completion is CompletionStatus.SKIPPED
    with pytest.raises(CompletedHistoryError):
        revise(
            reported,
            actor_id=OWNER,
            expected_version=2,
            changes=[RecordCompletion(PlanItemId("item-a"), CompletionStatus.COMPLETED)],
            now=at(hours=2),
        )


def test_unknown_duplicate_and_empty_changes_are_rejected() -> None:
    plan = make_plan(make_item("item-a"))

    with pytest.raises(UnknownPlanItemError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[RemoveItem(PlanItemId("item-zzz"))],
            now=at(hours=1),
        )
    with pytest.raises(DuplicatePlanItemError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[AddItem(make_item("item-a"))],
            now=at(hours=1),
        )
    with pytest.raises(EmptyRevisionError):
        revise(plan, actor_id=OWNER, expected_version=1, changes=[], now=at(hours=1))


def test_a_rejected_change_leaves_the_base_version_untouched() -> None:
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    with pytest.raises(UnknownPlanItemError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[
                RemoveItem(PlanItemId("item-a")),
                RemoveItem(PlanItemId("item-missing")),
            ],
            now=at(hours=1),
        )

    assert plan.item_ids() == {"item-a", "item-b"}
    assert plan.created_at == BASE_INSTANT


def test_replacement_may_not_smuggle_in_a_reported_outcome() -> None:
    plan = make_plan(make_item("item-a"))
    with pytest.raises(ValidationError):
        revise(
            plan,
            actor_id=OWNER,
            expected_version=1,
            changes=[ReplaceItem(make_item("item-a", completion=CompletionStatus.COMPLETED))],
            now=at(hours=1),
        )
