"""Plan storage in which ownership and version conflicts are database facts.

A plan version is identified by ``(plan_id, version)``, which is the table's
primary key. Two workers that both read version 2 and both try to write version
3 therefore cannot both succeed: the second insert conflicts, and the caller is
told its revision is stale rather than silently overwriting the first.
"""

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping

from health_assistant.adapters.persistence.mapping import (
    plan_item_rows,
    plan_row,
    plan_version_row,
    to_plan_version,
)
from health_assistant.adapters.persistence.schema import plan_items, plan_versions, plans
from health_assistant.domain.errors import OwnershipError, StalePlanRevisionError
from health_assistant.domain.identifiers import PlanId, UserId
from health_assistant.domain.plans import PlanVersion


class SqlPlanRepository:
    """Plan persistence scoped to one transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, version: PlanVersion) -> None:
        self._ensure_plan(version)
        inserted = self._connection.execute(
            insert(plan_versions)
            .values(plan_version_row(version))
            .on_conflict_do_nothing(index_elements=["plan_id", "version"])
        )
        if inserted.rowcount == 0:
            raise StalePlanRevisionError(
                expected=version.version, actual=self._highest_version(version.plan_id)
            )
        items = plan_item_rows(version)
        if items:
            self._connection.execute(insert(plan_items), items)

    def get(self, *, owner_id: UserId, plan_id: PlanId, version: int) -> PlanVersion | None:
        version_row = (
            self._connection.execute(
                select(plan_versions).where(
                    plan_versions.c.plan_id == plan_id,
                    plan_versions.c.version == version,
                    plan_versions.c.owner_id == owner_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if version_row is None:
            return None
        return self._load(owner_id=owner_id, plan_id=plan_id, version_row=version_row)

    def latest(self, *, owner_id: UserId, plan_id: PlanId) -> PlanVersion | None:
        version_row = (
            self._connection.execute(
                select(plan_versions)
                .where(
                    plan_versions.c.plan_id == plan_id,
                    plan_versions.c.owner_id == owner_id,
                )
                .order_by(plan_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if version_row is None:
            return None
        return self._load(owner_id=owner_id, plan_id=plan_id, version_row=version_row)

    def _load(
        self,
        *,
        owner_id: UserId,
        plan_id: PlanId,
        version_row: RowMapping,
    ) -> PlanVersion:
        item_rows = (
            self._connection.execute(
                select(plan_items).where(
                    plan_items.c.plan_id == plan_id,
                    plan_items.c.version == version_row["version"],
                    plan_items.c.owner_id == owner_id,
                )
            )
            .mappings()
            .all()
        )
        return to_plan_version(dict(version_row), [dict(row) for row in item_rows])

    def _ensure_plan(self, version: PlanVersion) -> None:
        """Create the plan row if absent, and refuse to write into another user's plan."""
        self._connection.execute(
            insert(plans)
            .values(plan_row(version))
            .on_conflict_do_nothing(index_elements=["plan_id"])
        )
        owner = self._connection.execute(
            select(plans.c.owner_id).where(plans.c.plan_id == version.plan_id)
        ).scalar_one()
        if owner != version.owner_id:
            raise OwnershipError(f"plan {version.plan_id!r} belongs to another user")

    def _highest_version(self, plan_id: PlanId) -> int:
        highest = self._connection.execute(
            select(plan_versions.c.version)
            .where(plan_versions.c.plan_id == plan_id)
            .order_by(plan_versions.c.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return int(highest) if highest is not None else 0
