"""Constraint invariants, normalization, expiry, and owner isolation."""

import pytest

from health_assistant.domain.constraints import (
    ConstraintKind,
    ConstraintSet,
    ConstraintSeverity,
    ConstraintSource,
    normalize_token,
)
from health_assistant.domain.errors import OwnershipError, ValidationError
from tests.support import (
    OTHER_USER,
    OWNER,
    at,
    make_constraint,
    window,
)


def test_subject_tokens_are_normalized_for_deterministic_matching() -> None:
    constraint = make_constraint("c-1", subject="  Peanut   Butter ")
    assert constraint.subject == "peanut butter"
    assert normalize_token("PEANUT\tbutter") == "peanut butter"


def test_schedule_constraint_requires_a_window_and_no_subject() -> None:
    with pytest.raises(ValidationError):
        make_constraint("c-1", kind=ConstraintKind.UNAVAILABLE_WINDOW, subject="peanut")


def test_token_constraint_requires_a_subject_and_no_window() -> None:
    with pytest.raises(ValidationError):
        make_constraint("c-1", kind=ConstraintKind.ALLERGY, window_override=window(start_hours=1))


def test_user_stated_constraints_are_confirmed_and_inferred_ones_are_not() -> None:
    stated = make_constraint("c-1", source=ConstraintSource.USER_STATED)
    inferred = make_constraint("c-2", source=ConstraintSource.INFERRED)

    assert stated.is_confirmed
    assert not inferred.is_confirmed


def test_severity_and_confirmation_are_independent_properties() -> None:
    inferred_hard = make_constraint(
        "c-1", severity=ConstraintSeverity.HARD, source=ConstraintSource.INFERRED
    )
    assert inferred_hard.severity is ConstraintSeverity.HARD
    assert not inferred_hard.is_confirmed


def test_expired_constraints_are_inactive() -> None:
    constraint = make_constraint("c-1", expires_at=at(hours=10))

    assert constraint.is_active_at(at(hours=9))
    assert not constraint.is_active_at(at(hours=10))


def test_constraint_set_rejects_another_users_constraint() -> None:
    foreign = make_constraint("c-1", owner=OTHER_USER)
    with pytest.raises(OwnershipError):
        ConstraintSet.of(OWNER, [foreign])


def test_constraint_set_rejects_duplicate_identifiers() -> None:
    with pytest.raises(ValidationError):
        ConstraintSet.of(OWNER, [make_constraint("c-1"), make_constraint("c-1")])
