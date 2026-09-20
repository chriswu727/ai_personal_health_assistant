"""Constraint storage, scoped to the owner on every access path."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_assistant.adapters.persistence.mapping import constraint_row, to_constraint
from health_assistant.adapters.persistence.schema import user_constraints
from health_assistant.domain.constraints import Constraint, ConstraintSet
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.identifiers import UserId
from health_assistant.domain.scheduling import require_utc

_MUTABLE_COLUMNS = (
    "kind",
    "severity",
    "source",
    "subject",
    "window_starts_at",
    "window_ends_at",
    "window_time_zone",
    "recorded_at",
    "expires_at",
)


class SqlConstraintRepository:
    """Constraint persistence scoped to one transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save(self, constraint: Constraint) -> None:
        """Store or replace a constraint, refusing to touch another user's row.

        The conflict update is conditional on the stored owner, so a collision
        with another user's identifier updates nothing and returns no row. That
        keeps the ownership decision inside one statement rather than in a
        read-then-write that another transaction could interleave with.
        """
        row = constraint_row(constraint)
        statement = insert(user_constraints).values(row)
        result = await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=["constraint_id"],
                set_={column: statement.excluded[column] for column in _MUTABLE_COLUMNS},
                where=user_constraints.c.owner_id == constraint.owner_id,
            ).returning(user_constraints.c.constraint_id)
        )
        if result.scalar_one_or_none() is None:
            raise OwnershipError(f"constraint {constraint.constraint_id!r} belongs to another user")

    async def all_for(self, owner_id: UserId) -> ConstraintSet:
        result = await self._connection.execute(
            select(user_constraints).where(user_constraints.c.owner_id == owner_id)
        )
        return ConstraintSet.of(owner_id, (to_constraint(dict(row)) for row in result.mappings()))

    async def active_at(self, owner_id: UserId, at: datetime) -> ConstraintSet:
        """Return the constraints that have not expired by ``at``."""
        instant = require_utc(at, "at")
        result = await self._connection.execute(
            select(user_constraints).where(
                user_constraints.c.owner_id == owner_id,
                (user_constraints.c.expires_at.is_(None))
                | (user_constraints.c.expires_at > instant),
            )
        )
        return ConstraintSet.of(owner_id, (to_constraint(dict(row)) for row in result.mappings()))
