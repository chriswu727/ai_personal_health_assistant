"""Deterministic checking of proposed plan items against user constraints.

This layer sits between any generated proposal and the approval that authorizes
external execution. It performs exact token and interval matching only: no model
call participates in the decision, so the same plan and constraint set always
produce the same findings.

A constraint the user never confirmed does not silently block and does not
silently pass. It yields ``REQUIRES_CLARIFICATION``, which blocks approval until
the user resolves it.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from health_assistant.domain.constraints import (
    SCHEDULE_KINDS,
    Constraint,
    ConstraintSet,
    ConstraintSeverity,
)
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.identifiers import ConstraintId, PlanItemId
from health_assistant.domain.plans import PlanItem, PlanVersion


class ValidationOutcome(StrEnum):
    """Why a constraint matched a proposed item."""

    VIOLATED = "violated"
    REQUIRES_CLARIFICATION = "requires_clarification"
    ADVISORY = "advisory"


BLOCKING_OUTCOMES = frozenset(
    {ValidationOutcome.VIOLATED, ValidationOutcome.REQUIRES_CLARIFICATION}
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One constraint matching one proposed item."""

    constraint_id: ConstraintId
    item_id: PlanItemId
    outcome: ValidationOutcome
    detail: str

    @property
    def is_blocking(self) -> bool:
        return self.outcome in BLOCKING_OUTCOMES


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The complete set of findings for a plan version."""

    findings: tuple[Finding, ...]

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.is_blocking)

    @property
    def is_blocking(self) -> bool:
        return any(finding.is_blocking for finding in self.findings)

    def for_items(self, item_ids: frozenset[PlanItemId]) -> "ValidationReport":
        """Narrow the report to the items an approval would actually cover."""
        return ValidationReport(
            findings=tuple(finding for finding in self.findings if finding.item_id in item_ids)
        )


def _outcome_for(constraint: Constraint) -> ValidationOutcome:
    if constraint.severity is ConstraintSeverity.SOFT:
        return ValidationOutcome.ADVISORY
    if constraint.is_confirmed:
        return ValidationOutcome.VIOLATED
    return ValidationOutcome.REQUIRES_CLARIFICATION


def _matches(constraint: Constraint, item: PlanItem) -> str | None:
    """Return a human-readable reason when ``constraint`` applies to ``item``."""
    if constraint.kind in SCHEDULE_KINDS:
        window = constraint.window
        if window is not None and window.overlaps(item.window):
            return f"item overlaps an unavailable window starting {window.start.isoformat()}"
        return None
    if constraint.subject in item.attributes:
        return f"item declares attribute {constraint.subject!r}"
    return None


def validate_plan(
    plan: PlanVersion,
    constraints: ConstraintSet,
    *,
    at: datetime,
) -> ValidationReport:
    """Check every still-proposed item against every active constraint.

    Items with a reported outcome are history and are not checked: adding a new
    constraint today must not retroactively invalidate what already happened.
    """
    if constraints.owner_id != plan.owner_id:
        raise OwnershipError("constraint set and plan belong to different users")

    findings: list[Finding] = []
    for item in plan.proposed_items():
        for constraint in constraints.active_at(at):
            detail = _matches(constraint, item)
            if detail is None:
                continue
            findings.append(
                Finding(
                    constraint_id=constraint.constraint_id,
                    item_id=item.item_id,
                    outcome=_outcome_for(constraint),
                    detail=detail,
                )
            )
    findings.sort(key=lambda finding: (finding.item_id, finding.constraint_id))
    return ValidationReport(findings=tuple(findings))
