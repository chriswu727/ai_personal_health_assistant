"""Translation between domain values and database rows.

The domain never sees a row and the schema never sees a domain object; this
module is the only place that knows both shapes.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from health_assistant.domain.identifiers import PlanId, PlanItemId, UserId
from health_assistant.domain.plans import (
    CompletionStatus,
    PlanItem,
    PlanItemCategory,
    PlanVersion,
)
from health_assistant.domain.scheduling import TimeWindow, require_utc


def plan_row(version: PlanVersion) -> dict[str, Any]:
    return {
        "plan_id": version.plan_id,
        "owner_id": version.owner_id,
        "created_at": version.created_at,
    }


def plan_version_row(version: PlanVersion) -> dict[str, Any]:
    return {
        "plan_id": version.plan_id,
        "version": version.version,
        "owner_id": version.owner_id,
        "parent_version": version.parent_version,
        "created_at": version.created_at,
    }


def plan_item_rows(version: PlanVersion) -> list[dict[str, Any]]:
    return [
        {
            "plan_id": version.plan_id,
            "version": version.version,
            "item_id": item.item_id,
            "owner_id": version.owner_id,
            "category": str(item.category),
            "title": item.title,
            "starts_at": item.window.start,
            "ends_at": item.window.end,
            "time_zone": item.window.time_zone,
            # Sorted so that a stored row is byte-comparable across writes.
            "attributes": sorted(item.attributes),
            "completion": str(item.completion),
        }
        for item in version.items
    ]


def to_plan_item(row: Mapping[str, Any]) -> PlanItem:
    return PlanItem(
        item_id=PlanItemId(row["item_id"]),
        category=PlanItemCategory(row["category"]),
        title=row["title"],
        window=TimeWindow(
            start=require_utc(row["starts_at"], "starts_at"),
            end=require_utc(row["ends_at"], "ends_at"),
            time_zone=row["time_zone"],
        ),
        attributes=frozenset(row["attributes"]),
        completion=CompletionStatus(row["completion"]),
    )


def to_plan_version(
    version_row: Mapping[str, Any], item_rows: Sequence[Mapping[str, Any]]
) -> PlanVersion:
    return PlanVersion(
        plan_id=PlanId(version_row["plan_id"]),
        owner_id=UserId(version_row["owner_id"]),
        version=version_row["version"],
        items=tuple(to_plan_item(row) for row in item_rows),
        created_at=require_utc(version_row["created_at"], "created_at"),
        parent_version=version_row["parent_version"],
    )
