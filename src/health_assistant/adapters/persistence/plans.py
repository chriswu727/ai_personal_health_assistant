"""Plan storage in which ownership and version conflicts are database facts.

A plan version is identified by ``(plan_id, version)``, which is the table's
primary key. Two clients that both read version 1 and both try to write version
2 therefore cannot both succeed: the second insert conflicts, and the caller is
told its revision is stale rather than silently overwriting the first.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

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

# The base version an initial plan version is written onto: none stored yet.
_NO_VERSION = 0


class SqlPlanRepository:
    """Plan persistence scoped to one transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save(self, version: PlanVersion) -> None:
        await self._ensure_plan(version)

        # A successor is only acceptable on top of its own persisted parent.
        # Key uniqueness alone would accept version 3 written onto version 1.
        base = version.parent_version or _NO_VERSION
        stored = await self._highest_version(version.plan_id)
        if base != stored:
            raise StalePlanRevisionError(expected=base, actual=stored)

        # RETURNING rather than rowcount: an INSERT's reported row count is not
        # guaranteed to be meaningful, while a DO NOTHING conflict returns no row.
        # This is the concurrent case, where another writer committed in between.
        result = await self._connection.execute(
            insert(plan_versions)
            .values(plan_version_row(version))
            .on_conflict_do_nothing(index_elements=["plan_id", "version"])
            .returning(plan_versions.c.version)
        )
        if result.scalar_one_or_none() is None:
            raise StalePlanRevisionError(
                expected=base, actual=await self._highest_version(version.plan_id)
            )
        items = plan_item_rows(version)
        if items:
            await self._connection.execute(insert(plan_items), items)

    async def get(self, *, owner_id: UserId, plan_id: PlanId, version: int) -> PlanVersion | None:
        result = await self._connection.execute(
            select(plan_versions).where(
                plan_versions.c.plan_id == plan_id,
                plan_versions.c.version == version,
                plan_versions.c.owner_id == owner_id,
            )
        )
        version_row = result.mappings().one_or_none()
        if version_row is None:
            return None
        return await self._load(owner_id=owner_id, plan_id=plan_id, version_row=version_row)

    async def latest(
        self, *, owner_id: UserId, plan_id: PlanId, for_update: bool = False
    ) -> PlanVersion | None:
        """Return the newest version, optionally serializing against a revision.

        A new version is an insert, so locking the version row would not hold
        anything back. ``for_update`` locks the plan row instead, which
        ``save`` also takes, making the plan row the point where a revision and
        a worker's authorization read order themselves.
        """
        if for_update:
            await self._lock_plan(plan_id)
        result = await self._connection.execute(
            select(plan_versions)
            .where(
                plan_versions.c.plan_id == plan_id,
                plan_versions.c.owner_id == owner_id,
            )
            .order_by(plan_versions.c.version.desc())
            .limit(1)
        )
        version_row = result.mappings().one_or_none()
        if version_row is None:
            return None
        return await self._load(owner_id=owner_id, plan_id=plan_id, version_row=version_row)

    async def _load(
        self,
        *,
        owner_id: UserId,
        plan_id: PlanId,
        version_row: RowMapping,
    ) -> PlanVersion:
        result = await self._connection.execute(
            select(plan_items).where(
                plan_items.c.plan_id == plan_id,
                plan_items.c.version == version_row["version"],
                plan_items.c.owner_id == owner_id,
            )
        )
        item_rows = result.mappings().all()
        return to_plan_version(dict(version_row), [dict(row) for row in item_rows])

    async def _ensure_plan(self, version: PlanVersion) -> None:
        """Create the plan row if absent, and refuse to write into another user's plan."""
        await self._connection.execute(
            insert(plans)
            .values(plan_row(version))
            .on_conflict_do_nothing(index_elements=["plan_id"])
        )
        if await self._lock_plan(version.plan_id) != version.owner_id:
            raise OwnershipError(f"plan {version.plan_id!r} belongs to another user")

    async def _lock_plan(self, plan_id: PlanId) -> str | None:
        """Hold the plan row, which orders revisions against authorization reads."""
        result = await self._connection.execute(
            select(plans.c.owner_id).where(plans.c.plan_id == plan_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _highest_version(self, plan_id: PlanId) -> int:
        result = await self._connection.execute(
            select(plan_versions.c.version)
            .where(plan_versions.c.plan_id == plan_id)
            .order_by(plan_versions.c.version.desc())
            .limit(1)
        )
        highest = result.scalar_one_or_none()
        return int(highest) if highest is not None else 0
