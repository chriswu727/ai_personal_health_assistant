"""The phase-one journey from docs/PRODUCT_SCOPE.md, exercised at domain level.

A synthetic user states constraints, receives a plan, edits one activity,
approves a subset, loses the provider response, recovers without a duplicate
write, and finally reports a missed session. No provider, database, or model is
involved: this establishes the deterministic contract that later adapters obey.
"""

from datetime import timedelta

import pytest

from health_assistant.domain.approvals import authorize_execution, grant_approval
from health_assistant.domain.constraints import ConstraintKind
from health_assistant.domain.errors import (
    ApprovalVersionMismatchError,
    PlanNotApprovableError,
    ReconciliationRequiredError,
)
from health_assistant.domain.identifiers import ApprovalId, OperationId, PlanItemId
from health_assistant.domain.operations import (
    OperationKind,
    OperationState,
    ProviderOutcome,
    claim,
    confirm,
    propose,
    reconcile,
    record_ambiguous_outcome,
    request_confirmation,
    retry,
)
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItemCategory,
    RecordCompletion,
    ReplaceItem,
    revise,
)
from health_assistant.domain.validation import ValidationOutcome, validate_plan
from tests.support import (
    OWNER,
    at,
    make_constraint,
    make_constraint_set,
    make_item,
    make_plan,
    window,
)

WALK = PlanItemId("item-walk")
DINNER = PlanItemId("item-dinner")


def test_first_journey_recovers_from_an_ambiguous_calendar_write() -> None:
    # 1. The user states a confirmed allergy and one unavailable evening.
    constraints = make_constraint_set(
        make_constraint("c-allergy", kind=ConstraintKind.ALLERGY, subject="peanut"),
        make_constraint(
            "c-busy",
            kind=ConstraintKind.UNAVAILABLE_WINDOW,
            window_override=window(start_hours=72, duration_hours=3),
        ),
    )

    # 2. The first proposal violates the allergy, so it cannot be approved.
    proposed = make_plan(
        make_item(WALK, title="Evening walk", start_hours=24, duration_hours=1),
        make_item(
            DINNER,
            category=PlanItemCategory.NUTRITION,
            title="Satay bowl",
            attributes=("peanut", "rice"),
            start_hours=27,
        ),
    )
    first_report = validate_plan(proposed, constraints, at=at())
    assert [finding.outcome for finding in first_report.blocking] == [ValidationOutcome.VIOLATED]
    with pytest.raises(PlanNotApprovableError):
        grant_approval(
            approval_id=ApprovalId("approval-1"),
            plan=proposed,
            constraints=constraints,
            scope=frozenset({WALK, DINNER}),
            actor_id=OWNER,
            now=at(),
            ttl=timedelta(minutes=30),
        )

    # 3. The user edits only the meal; the walk is carried over untouched.
    corrected = revise(
        proposed,
        actor_id=OWNER,
        expected_version=1,
        changes=[
            ReplaceItem(
                make_item(
                    DINNER,
                    category=PlanItemCategory.NUTRITION,
                    title="Sesame tofu bowl",
                    attributes=("sesame", "rice"),
                    start_hours=27,
                )
            )
        ],
        now=at(minutes=1),
    )
    assert corrected.item(WALK) == proposed.item(WALK)
    assert not validate_plan(corrected, constraints, at=at(minutes=1)).is_blocking

    # 4. The user approves calendar changes for the walk only.
    approval = grant_approval(
        approval_id=ApprovalId("approval-1"),
        plan=corrected,
        constraints=constraints,
        scope=frozenset({WALK}),
        actor_id=OWNER,
        now=at(minutes=2),
        ttl=timedelta(minutes=30),
    )
    operation = confirm(
        request_confirmation(
            propose(
                operation_id=OperationId("op-walk"),
                plan=corrected,
                item_id=WALK,
                kind=OperationKind.CREATE_EVENT,
                now=at(minutes=2),
            ),
            now=at(minutes=3),
        ),
        approval=approval,
        plan=corrected,
        actor_id=OWNER,
        now=at(minutes=4),
    )

    # 5. The provider response is lost after the write may already have landed.
    executing = claim(
        operation, worker_id="worker-1", now=at(minutes=5), lease_duration=timedelta(minutes=5)
    )
    unknown = record_ambiguous_outcome(executing, reason="provider timeout", now=at(minutes=6))
    with pytest.raises(ReconciliationRequiredError):
        retry(unknown, now=at(minutes=7))

    # Reconciliation finds the event was in fact created: no second write occurs.
    settled = reconcile(
        unknown,
        outcome=ProviderOutcome(applied=True, external_ref="evt-synthetic-walk"),
        now=at(minutes=8),
    )
    assert settled.state is OperationState.SUCCEEDED
    assert settled.attempts == 1
    assert settled.external_ref == "evt-synthetic-walk"

    # 6. The user edits an unrelated meal. The confirmation has not expired, but it
    #    described plan version 2 and therefore no longer authorizes anything.
    adjusted = revise(
        corrected,
        actor_id=OWNER,
        expected_version=2,
        changes=[
            ReplaceItem(
                make_item(
                    DINNER,
                    category=PlanItemCategory.NUTRITION,
                    title="Sesame tofu bowl with greens",
                    attributes=("sesame", "rice", "kale"),
                    start_hours=27,
                )
            )
        ],
        now=at(minutes=10),
    )
    assert not approval.is_expired_at(at(minutes=10))
    with pytest.raises(ApprovalVersionMismatchError):
        authorize_execution(
            approval,
            plan=adjusted,
            item_ids=frozenset({WALK}),
            actor_id=OWNER,
            now=at(minutes=10),
        )

    # 7. A day later the user reports the walk as missed. History is preserved and
    #    the meal the user last chose is carried forward untouched.
    reflected = revise(
        adjusted,
        actor_id=OWNER,
        expected_version=3,
        changes=[RecordCompletion(WALK, CompletionStatus.SKIPPED)],
        now=at(hours=30),
    )

    assert reflected.version == 4
    assert reflected.item(WALK).completion is CompletionStatus.SKIPPED
    assert reflected.item(DINNER) == adjusted.item(DINNER)
    assert [item.item_id for item in reflected.proposed_items()] == [DINNER]
    assert settled.external_ref == "evt-synthetic-walk", "the confirmed write survives"
