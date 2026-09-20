"""Deterministic synthetic fixtures shared by the domain tests.

No fixture describes a real person. Every instant derives from ``BASE_INSTANT``
so that test outcomes never depend on the wall clock.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from health_assistant.domain.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSet,
    ConstraintSeverity,
    ConstraintSource,
)
from health_assistant.domain.identifiers import (
    ConstraintId,
    PlanId,
    PlanItemId,
    UserId,
)
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItem,
    PlanItemCategory,
    PlanVersion,
)
from health_assistant.domain.scheduling import TimeWindow

BASE_INSTANT = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
OWNER = UserId("user-synthetic-001")
OTHER_USER = UserId("user-synthetic-002")
PLAN = PlanId("plan-synthetic-001")
DEFAULT_ZONE = "America/Toronto"


@dataclass(frozen=True, slots=True)
class FixedClock:
    """A clock that never advances unless a test asks it to."""

    instant: datetime

    def now(self) -> datetime:
        return self.instant

    def plus(self, **delta: float) -> "FixedClock":
        return FixedClock(self.instant + timedelta(**delta))


def at(**delta: float) -> datetime:
    """Return an instant offset from ``BASE_INSTANT``."""
    return BASE_INSTANT + timedelta(**delta)


def window(
    *,
    start_hours: float = 24,
    duration_hours: float = 1,
    time_zone: str = DEFAULT_ZONE,
) -> TimeWindow:
    start = at(hours=start_hours)
    return TimeWindow(start=start, end=start + timedelta(hours=duration_hours), time_zone=time_zone)


def make_item(
    item_id: str,
    *,
    category: PlanItemCategory = PlanItemCategory.EXERCISE,
    title: str = "Evening walk",
    attributes: tuple[str, ...] = (),
    start_hours: float = 24,
    duration_hours: float = 1,
    completion: CompletionStatus = CompletionStatus.UNREPORTED,
) -> PlanItem:
    return PlanItem(
        item_id=PlanItemId(item_id),
        category=category,
        title=title,
        window=window(start_hours=start_hours, duration_hours=duration_hours),
        attributes=frozenset(attributes),
        completion=completion,
    )


def make_plan(*items: PlanItem, owner: UserId = OWNER) -> PlanVersion:
    return PlanVersion.initial(plan_id=PLAN, owner_id=owner, items=items, created_at=BASE_INSTANT)


def make_constraint(
    constraint_id: str,
    *,
    kind: ConstraintKind = ConstraintKind.ALLERGY,
    severity: ConstraintSeverity = ConstraintSeverity.HARD,
    source: ConstraintSource = ConstraintSource.USER_STATED,
    subject: str = "peanut",
    window_override: TimeWindow | None = None,
    expires_at: datetime | None = None,
    owner: UserId = OWNER,
) -> Constraint:
    return Constraint(
        constraint_id=ConstraintId(constraint_id),
        owner_id=owner,
        kind=kind,
        severity=severity,
        source=source,
        recorded_at=BASE_INSTANT,
        subject="" if window_override is not None else subject,
        window=window_override,
        expires_at=expires_at,
    )


def make_constraint_set(*constraints: Constraint, owner: UserId = OWNER) -> ConstraintSet:
    return ConstraintSet.of(owner, constraints)


EMPTY_CONSTRAINTS = make_constraint_set()
