"""User constraints treated as first-class, machine-checkable domain objects.

Constraints carry two independent properties. ``severity`` describes how
damaging a violation is; ``source`` describes whether the user confirmed the
fact or the system inferred it. Keeping them separate lets an unconfirmed
allergy force a clarifying question instead of being either silently enforced
or silently ignored.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from health_assistant.domain.errors import OwnershipError, ValidationError
from health_assistant.domain.identifiers import ConstraintId, UserId, require_identifier
from health_assistant.domain.scheduling import TimeWindow, require_utc


class ConstraintKind(StrEnum):
    ALLERGY = "allergy"
    DIETARY_EXCLUSION = "dietary_exclusion"
    MOVEMENT_LIMITATION = "movement_limitation"
    EQUIPMENT_UNAVAILABLE = "equipment_unavailable"
    UNAVAILABLE_WINDOW = "unavailable_window"


class ConstraintSeverity(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ConstraintSource(StrEnum):
    USER_STATED = "user_stated"
    INFERRED = "inferred"


SCHEDULE_KINDS = frozenset({ConstraintKind.UNAVAILABLE_WINDOW})


def normalize_token(value: str) -> str:
    """Return the canonical matching form of a subject or attribute token."""
    return " ".join(value.strip().casefold().split())


@dataclass(frozen=True, slots=True)
class Constraint:
    """A single restriction that proposed plan items must respect."""

    constraint_id: ConstraintId
    owner_id: UserId
    kind: ConstraintKind
    severity: ConstraintSeverity
    source: ConstraintSource
    recorded_at: datetime
    subject: str = ""
    window: TimeWindow | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "constraint_id", require_identifier(self.constraint_id, "constraint_id")
        )
        object.__setattr__(self, "owner_id", require_identifier(self.owner_id, "owner_id"))
        object.__setattr__(self, "subject", normalize_token(self.subject))
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, "recorded_at"))
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))

        if self.kind in SCHEDULE_KINDS:
            if self.window is None:
                raise ValidationError(f"{self.kind} requires a window")
            if self.subject:
                raise ValidationError(f"{self.kind} must not carry a subject token")
        else:
            if not self.subject:
                raise ValidationError(f"{self.kind} requires a subject token")
            if self.window is not None:
                raise ValidationError(f"{self.kind} must not carry a window")

    @property
    def is_confirmed(self) -> bool:
        return self.source is ConstraintSource.USER_STATED

    def is_active_at(self, instant: datetime) -> bool:
        moment = require_utc(instant, "instant")
        return self.expires_at is None or moment < self.expires_at


@dataclass(frozen=True, slots=True)
class ConstraintSet:
    """The constraints belonging to exactly one user."""

    owner_id: UserId
    constraints: tuple[Constraint, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", require_identifier(self.owner_id, "owner_id"))
        ordered = tuple(sorted(self.constraints, key=lambda item: item.constraint_id))
        for constraint in ordered:
            if constraint.owner_id != self.owner_id:
                raise OwnershipError(
                    f"constraint {constraint.constraint_id!r} belongs to another user"
                )
        identifiers = [constraint.constraint_id for constraint in ordered]
        if len(set(identifiers)) != len(identifiers):
            raise ValidationError("constraint identifiers must be unique within a set")
        object.__setattr__(self, "constraints", ordered)

    @classmethod
    def of(cls, owner_id: UserId, constraints: Iterable[Constraint]) -> "ConstraintSet":
        return cls(owner_id=owner_id, constraints=tuple(constraints))

    def active_at(self, instant: datetime) -> tuple[Constraint, ...]:
        return tuple(item for item in self.constraints if item.is_active_at(instant))

    def __iter__(self) -> Iterator[Constraint]:
        return iter(self.constraints)

    def __len__(self) -> int:
        return len(self.constraints)
