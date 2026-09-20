"""Immutable weekly plan versions and the rules governing their revision.

A revision never mutates a version in place. It produces a successor whose
number increases by one, leaves untouched items byte-for-byte identical, and
refuses to rewrite any item whose outcome the user already reported.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from health_assistant.domain.constraints import normalize_token
from health_assistant.domain.errors import (
    CompletedHistoryError,
    DuplicatePlanItemError,
    EmptyRevisionError,
    OwnershipError,
    StalePlanRevisionError,
    UnknownPlanItemError,
    ValidationError,
)
from health_assistant.domain.identifiers import (
    PlanId,
    PlanItemId,
    UserId,
    require_identifier,
)
from health_assistant.domain.scheduling import TimeWindow, require_utc


class PlanItemCategory(StrEnum):
    EXERCISE = "exercise"
    NUTRITION = "nutrition"
    SLEEP = "sleep"
    ROUTINE = "routine"


class CompletionStatus(StrEnum):
    """What the user reported about an item.

    ``UNREPORTED`` means no record exists, which is distinct from a reported
    miss: absence of a record is never evidence of completion.
    """

    UNREPORTED = "unreported"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One scheduled activity with the attributes constraint checks rely on."""

    item_id: PlanItemId
    category: PlanItemCategory
    title: str
    window: TimeWindow
    attributes: frozenset[str] = frozenset()
    completion: CompletionStatus = CompletionStatus.UNREPORTED

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", require_identifier(self.item_id, "item_id"))
        title = self.title.strip()
        if not title:
            raise ValidationError("plan item title must not be blank")
        object.__setattr__(self, "title", title)
        object.__setattr__(
            self,
            "attributes",
            frozenset(normalize_token(value) for value in self.attributes if value.strip()),
        )

    @property
    def is_reported(self) -> bool:
        """Whether the user recorded an outcome, making this item history."""
        return self.completion is not CompletionStatus.UNREPORTED


@dataclass(frozen=True, slots=True)
class AddItem:
    item: PlanItem


@dataclass(frozen=True, slots=True)
class ReplaceItem:
    item: PlanItem


@dataclass(frozen=True, slots=True)
class RemoveItem:
    item_id: PlanItemId


@dataclass(frozen=True, slots=True)
class RecordCompletion:
    item_id: PlanItemId
    status: CompletionStatus


PlanChange = AddItem | ReplaceItem | RemoveItem | RecordCompletion


def _sort_key(item: PlanItem) -> tuple[datetime, str]:
    return (item.window.start, item.item_id)


@dataclass(frozen=True, slots=True)
class PlanVersion:
    """An immutable snapshot of a plan at one revision number."""

    plan_id: PlanId
    owner_id: UserId
    version: int
    items: tuple[PlanItem, ...]
    created_at: datetime
    parent_version: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_identifier(self.plan_id, "plan_id"))
        object.__setattr__(self, "owner_id", require_identifier(self.owner_id, "owner_id"))
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        if self.version < 1:
            raise ValidationError("plan version must start at 1")
        if (self.version == 1) != (self.parent_version is None):
            raise ValidationError("only the first version may omit a parent version")
        if self.parent_version is not None and self.parent_version != self.version - 1:
            raise ValidationError("a version's parent must be the version immediately before it")
        identifiers = [item.item_id for item in self.items]
        if len(set(identifiers)) != len(identifiers):
            raise ValidationError("plan item identifiers must be unique within a version")
        object.__setattr__(self, "items", tuple(sorted(self.items, key=_sort_key)))

    @classmethod
    def initial(
        cls,
        *,
        plan_id: PlanId,
        owner_id: UserId,
        items: Sequence[PlanItem],
        created_at: datetime,
    ) -> "PlanVersion":
        return cls(
            plan_id=plan_id,
            owner_id=owner_id,
            version=1,
            items=tuple(items),
            created_at=created_at,
            parent_version=None,
        )

    def item(self, item_id: PlanItemId) -> PlanItem:
        for candidate in self.items:
            if candidate.item_id == item_id:
                return candidate
        raise UnknownPlanItemError(item_id)

    def item_ids(self) -> frozenset[PlanItemId]:
        return frozenset(item.item_id for item in self.items)

    def proposed_items(self) -> tuple[PlanItem, ...]:
        """Items with no reported outcome: the only items still executable."""
        return tuple(item for item in self.items if not item.is_reported)


def _apply_add(working: dict[PlanItemId, PlanItem], change: AddItem) -> None:
    if change.item.item_id in working:
        raise DuplicatePlanItemError(change.item.item_id)
    if change.item.is_reported:
        raise ValidationError("a new plan item must start without a reported outcome")
    working[change.item.item_id] = change.item


def _apply_replace(working: dict[PlanItemId, PlanItem], change: ReplaceItem) -> None:
    _require_mutable(working, change.item.item_id)
    if change.item.is_reported:
        raise ValidationError("use RecordCompletion to report an outcome, not ReplaceItem")
    working[change.item.item_id] = change.item


def _apply_remove(working: dict[PlanItemId, PlanItem], change: RemoveItem) -> None:
    _require_mutable(working, change.item_id)
    del working[change.item_id]


def _apply_completion(working: dict[PlanItemId, PlanItem], change: RecordCompletion) -> None:
    existing = _require_mutable(working, change.item_id)
    if change.status is CompletionStatus.UNREPORTED:
        raise ValidationError("a completion record must not be UNREPORTED")
    working[change.item_id] = replace(existing, completion=change.status)


def _require_mutable(working: dict[PlanItemId, PlanItem], item_id: PlanItemId) -> PlanItem:
    """Return the item, rejecting unknown identifiers and reported history."""
    existing = working.get(item_id)
    if existing is None:
        raise UnknownPlanItemError(item_id)
    if existing.is_reported:
        raise CompletedHistoryError(item_id)
    return existing


def _apply(working: dict[PlanItemId, PlanItem], change: PlanChange) -> None:
    match change:
        case AddItem():
            _apply_add(working, change)
        case ReplaceItem():
            _apply_replace(working, change)
        case RemoveItem():
            _apply_remove(working, change)
        case RecordCompletion():
            _apply_completion(working, change)


def revise(
    base: PlanVersion,
    *,
    actor_id: UserId,
    expected_version: int,
    changes: Sequence[PlanChange],
    now: datetime,
) -> PlanVersion:
    """Return the successor version produced by applying ``changes`` to ``base``.

    Raises before making any change if the actor is not the owner, if the base
    moved on concurrently, or if a change targets reported history.
    """
    if actor_id != base.owner_id:
        raise OwnershipError(f"user {actor_id!r} may not revise plan {base.plan_id!r}")
    if expected_version != base.version:
        raise StalePlanRevisionError(expected=expected_version, actual=base.version)
    if not changes:
        raise EmptyRevisionError()

    working: dict[PlanItemId, PlanItem] = {item.item_id: item for item in base.items}
    for change in changes:
        _apply(working, change)

    return PlanVersion(
        plan_id=base.plan_id,
        owner_id=base.owner_id,
        version=base.version + 1,
        items=tuple(working.values()),
        created_at=now,
        parent_version=base.version,
    )
