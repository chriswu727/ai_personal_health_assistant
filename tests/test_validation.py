"""Deterministic constraint checking of proposed plan items."""

import pytest

from health_assistant.domain.constraints import (
    ConstraintKind,
    ConstraintSeverity,
    ConstraintSource,
)
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.plans import CompletionStatus, PlanItemCategory
from health_assistant.domain.validation import ValidationOutcome, validate_plan
from tests.support import (
    OTHER_USER,
    at,
    make_constraint,
    make_constraint_set,
    make_item,
    make_plan,
    window,
)


@pytest.mark.parametrize(
    ("severity", "source", "expected"),
    [
        (
            ConstraintSeverity.HARD,
            ConstraintSource.USER_STATED,
            ValidationOutcome.VIOLATED,
        ),
        (
            ConstraintSeverity.HARD,
            ConstraintSource.INFERRED,
            ValidationOutcome.REQUIRES_CLARIFICATION,
        ),
        (
            ConstraintSeverity.SOFT,
            ConstraintSource.USER_STATED,
            ValidationOutcome.ADVISORY,
        ),
        (
            ConstraintSeverity.SOFT,
            ConstraintSource.INFERRED,
            ValidationOutcome.ADVISORY,
        ),
    ],
)
def test_outcome_depends_on_severity_and_confirmation(
    severity: ConstraintSeverity,
    source: ConstraintSource,
    expected: ValidationOutcome,
) -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("peanut",))
    )
    constraints = make_constraint_set(
        make_constraint("c-1", severity=severity, source=source, subject="peanut")
    )

    report = validate_plan(plan, constraints, at=at())

    assert [finding.outcome for finding in report.findings] == [expected]


def test_an_unconfirmed_hard_constraint_blocks_until_clarified() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("peanut",))
    )
    constraints = make_constraint_set(
        make_constraint("c-1", source=ConstraintSource.INFERRED, subject="peanut")
    )

    report = validate_plan(plan, constraints, at=at())

    assert report.is_blocking
    assert report.blocking[0].outcome is ValidationOutcome.REQUIRES_CLARIFICATION


def test_advisory_findings_do_not_block() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("cilantro",))
    )
    constraints = make_constraint_set(
        make_constraint(
            "c-1",
            kind=ConstraintKind.DIETARY_EXCLUSION,
            severity=ConstraintSeverity.SOFT,
            subject="cilantro",
        )
    )

    report = validate_plan(plan, constraints, at=at())

    assert report.findings
    assert not report.is_blocking


def test_matching_ignores_case_and_surrounding_whitespace() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("  Peanut Butter ",))
    )
    constraints = make_constraint_set(make_constraint("c-1", subject="PEANUT butter"))

    assert validate_plan(plan, constraints, at=at()).is_blocking


def test_unrelated_attributes_produce_no_findings() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("lentil",))
    )
    constraints = make_constraint_set(make_constraint("c-1", subject="peanut"))

    assert validate_plan(plan, constraints, at=at()).findings == ()


def test_an_expired_constraint_is_not_applied() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("peanut",))
    )
    constraints = make_constraint_set(
        make_constraint("c-1", subject="peanut", expires_at=at(hours=1))
    )

    assert validate_plan(plan, constraints, at=at()).is_blocking
    assert not validate_plan(plan, constraints, at=at(hours=2)).is_blocking


def test_unavailable_windows_are_checked_by_interval_overlap() -> None:
    plan = make_plan(make_item("item-a", start_hours=24, duration_hours=2))
    overlapping = make_constraint_set(
        make_constraint(
            "c-1",
            kind=ConstraintKind.UNAVAILABLE_WINDOW,
            window_override=window(start_hours=25, duration_hours=1),
        )
    )
    adjacent = make_constraint_set(
        make_constraint(
            "c-1",
            kind=ConstraintKind.UNAVAILABLE_WINDOW,
            window_override=window(start_hours=26, duration_hours=1),
        )
    )

    assert validate_plan(plan, overlapping, at=at()).is_blocking
    assert not validate_plan(plan, adjacent, at=at()).is_blocking


def test_reported_items_are_history_and_are_not_revalidated() -> None:
    plan = make_plan(
        make_item(
            "item-a",
            category=PlanItemCategory.NUTRITION,
            attributes=("peanut",),
            completion=CompletionStatus.COMPLETED,
        )
    )
    constraints = make_constraint_set(make_constraint("c-1", subject="peanut"))

    assert validate_plan(plan, constraints, at=at()).findings == ()


def test_constraints_from_another_user_are_refused() -> None:
    plan = make_plan(make_item("item-a"))
    foreign = make_constraint_set(make_constraint("c-1", owner=OTHER_USER), owner=OTHER_USER)

    with pytest.raises(OwnershipError):
        validate_plan(plan, foreign, at=at())


def test_findings_are_deterministically_ordered() -> None:
    plan = make_plan(
        make_item("item-b", category=PlanItemCategory.NUTRITION, attributes=("peanut",)),
        make_item(
            "item-a",
            category=PlanItemCategory.NUTRITION,
            attributes=("peanut", "shellfish"),
            start_hours=48,
        ),
    )
    constraints = make_constraint_set(
        make_constraint("c-2", subject="shellfish"),
        make_constraint("c-1", subject="peanut"),
    )

    report = validate_plan(plan, constraints, at=at())

    assert [(f.item_id, f.constraint_id) for f in report.findings] == [
        ("item-a", "c-1"),
        ("item-a", "c-2"),
        ("item-b", "c-1"),
    ]
