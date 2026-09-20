"""Approval binding: owner, payload fingerprint, scope, and expiry."""

from datetime import datetime, timedelta

import pytest

from health_assistant.domain.actions import ApprovedAction, OperationKind
from health_assistant.domain.approvals import (
    Approval,
    authorize_execution,
    fingerprint_items,
    fingerprint_scope,
    grant_approval,
)
from health_assistant.domain.constraints import ConstraintSet, ConstraintSource
from health_assistant.domain.errors import (
    ApprovalActionNotAuthorizedError,
    ApprovalExpiredError,
    ApprovalPayloadChangedError,
    ApprovalRevokedError,
    ApprovalScopeError,
    ApprovalVersionMismatchError,
    OwnershipError,
    PlanNotApprovableError,
)
from health_assistant.domain.identifiers import ApprovalId, PlanItemId
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItemCategory,
    PlanVersion,
    RecordCompletion,
    ReplaceItem,
    revise,
)
from tests.support import (
    EMPTY_CONSTRAINTS,
    OTHER_USER,
    OWNER,
    at,
    make_constraint,
    make_constraint_set,
    make_item,
    make_plan,
    make_scope,
)

TTL = timedelta(minutes=30)
SCOPE = make_scope("item-a")


def _approve(
    plan: PlanVersion,
    constraints: ConstraintSet = EMPTY_CONSTRAINTS,
    scope: frozenset[ApprovedAction] = SCOPE,
    now: datetime | None = None,
) -> Approval:
    return grant_approval(
        approval_id=ApprovalId("approval-1"),
        plan=plan,
        constraints=constraints,
        scope=scope,
        actor_id=OWNER,
        now=now if now is not None else at(),
        ttl=TTL,
    )


def test_fingerprint_is_stable_regardless_of_input_ordering() -> None:
    first = make_item("item-a", attributes=("walk", "outdoors"))
    second = make_item("item-b", attributes=("outdoors", "walk"), start_hours=48)

    assert fingerprint_items([first, second]) == fingerprint_items([second, first])


def test_fingerprint_changes_when_visible_content_changes() -> None:
    original = make_item("item-a", title="Evening walk")
    edited = make_item("item-a", title="Morning walk")

    assert fingerprint_items([original]) != fingerprint_items([edited])


def test_approval_records_the_scope_version_and_expiry() -> None:
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = _approve(plan)

    assert approval.plan_version == 1
    assert approval.scope == SCOPE
    assert approval.expires_at == at() + TTL
    assert not approval.is_revoked


def test_a_blocking_finding_prevents_approval() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("peanut",))
    )
    constraints = make_constraint_set(make_constraint("c-1", subject="peanut"))

    with pytest.raises(PlanNotApprovableError):
        _approve(plan, constraints)


def test_an_unconfirmed_hard_constraint_also_prevents_approval() -> None:
    plan = make_plan(
        make_item("item-a", category=PlanItemCategory.NUTRITION, attributes=("peanut",))
    )
    constraints = make_constraint_set(
        make_constraint("c-1", subject="peanut", source=ConstraintSource.INFERRED)
    )

    with pytest.raises(PlanNotApprovableError):
        _approve(plan, constraints)


def test_findings_outside_the_requested_scope_do_not_block() -> None:
    plan = make_plan(
        make_item("item-a", title="Evening walk"),
        make_item(
            "item-b",
            category=PlanItemCategory.NUTRITION,
            attributes=("peanut",),
            start_hours=48,
        ),
    )
    constraints = make_constraint_set(make_constraint("c-1", subject="peanut"))

    approval = _approve(plan, constraints)

    assert approval.scope == SCOPE


def test_another_user_may_not_approve_the_plan() -> None:
    plan = make_plan(make_item("item-a"))
    with pytest.raises(OwnershipError):
        grant_approval(
            approval_id=ApprovalId("approval-1"),
            plan=plan,
            constraints=EMPTY_CONSTRAINTS,
            scope=SCOPE,
            actor_id=OTHER_USER,
            now=at(),
            ttl=TTL,
        )


def test_scope_must_name_existing_unreported_items() -> None:
    plan = make_plan(make_item("item-a"))
    with pytest.raises(ApprovalScopeError):
        _approve(plan, scope=make_scope("item-missing"))

    reported = make_plan(
        make_item("item-a", completion=CompletionStatus.COMPLETED),
        make_item("item-b", start_hours=48),
    )
    with pytest.raises(ApprovalScopeError):
        _approve(reported)


def test_a_valid_approval_authorizes_its_scope() -> None:
    plan = make_plan(make_item("item-a"))
    approval = _approve(plan)

    authorize_execution(approval, plan=plan, actions=SCOPE, actor_id=OWNER, now=at(minutes=5))


def test_expired_and_revoked_approvals_authorize_nothing() -> None:
    plan = make_plan(make_item("item-a"))
    approval = _approve(plan)

    with pytest.raises(ApprovalExpiredError):
        authorize_execution(approval, plan=plan, actions=SCOPE, actor_id=OWNER, now=at(minutes=30))

    revoked = approval.revoke(at=at(minutes=1))
    with pytest.raises(ApprovalRevokedError):
        authorize_execution(revoked, plan=plan, actions=SCOPE, actor_id=OWNER, now=at(minutes=5))


def test_a_wrong_owner_cannot_use_an_approval() -> None:
    plan = make_plan(make_item("item-a"))
    approval = _approve(plan)

    with pytest.raises(OwnershipError):
        authorize_execution(
            approval, plan=plan, actions=SCOPE, actor_id=OTHER_USER, now=at(minutes=5)
        )


def test_items_outside_the_approved_scope_are_refused() -> None:
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = _approve(plan)

    with pytest.raises(ApprovalScopeError):
        authorize_execution(
            approval,
            plan=plan,
            actions=make_scope("item-b"),
            actor_id=OWNER,
            now=at(minutes=5),
        )


def test_editing_the_approved_item_invalidates_the_approval() -> None:
    plan = make_plan(make_item("item-a"))
    approval = _approve(plan)
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[ReplaceItem(make_item("item-a", title="Morning walk"))],
        now=at(minutes=1),
    )

    with pytest.raises(ApprovalVersionMismatchError):
        authorize_execution(
            approval, plan=revised, actions=SCOPE, actor_id=OWNER, now=at(minutes=5)
        )


def test_editing_an_unrelated_item_also_invalidates_the_approval() -> None:
    """Any revision produces a new version, so confirmation is deliberately conservative."""
    plan = make_plan(make_item("item-a"), make_item("item-b", start_hours=48))
    approval = _approve(plan)
    revised = revise(
        plan,
        actor_id=OWNER,
        expected_version=1,
        changes=[RecordCompletion(PlanItemId("item-b"), CompletionStatus.COMPLETED)],
        now=at(minutes=1),
    )

    with pytest.raises(ApprovalVersionMismatchError):
        authorize_execution(
            approval, plan=revised, actions=SCOPE, actor_id=OWNER, now=at(minutes=5)
        )


def test_matching_version_with_different_content_is_still_refused() -> None:
    """Guards against a store that reuses a version number for changed content."""
    plan = make_plan(make_item("item-a", title="Evening walk"))
    approval = _approve(plan)
    forged = make_plan(make_item("item-a", title="Morning walk"))

    with pytest.raises(ApprovalPayloadChangedError):
        authorize_execution(approval, plan=forged, actions=SCOPE, actor_id=OWNER, now=at(minutes=5))


def test_an_approval_does_not_authorize_a_different_action_on_the_same_item() -> None:
    """A confirmation to create an event is not a confirmation to cancel one."""
    plan = make_plan(make_item("item-a"))
    approval = _approve(plan)

    with pytest.raises(ApprovalActionNotAuthorizedError):
        authorize_execution(
            approval,
            plan=plan,
            actions=make_scope("item-a", kind=OperationKind.CANCEL_EVENT),
            actor_id=OWNER,
            now=at(minutes=5),
        )


def test_the_fingerprint_distinguishes_the_approved_action() -> None:
    plan = make_plan(make_item("item-a"))
    create = fingerprint_scope(plan, make_scope("item-a"))
    cancel = fingerprint_scope(plan, make_scope("item-a", kind=OperationKind.CANCEL_EVENT))

    assert create != cancel
