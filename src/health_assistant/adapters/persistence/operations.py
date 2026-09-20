"""Durable storage for external operations, including worker claiming.

Most methods are scoped to an owner like every other repository. ``claim_next``
is not, and deliberately: a worker serves every user's queue. It returns only an
operation to work on, and the caller must then load that operation's plan and
approval with the operation's own owner, so authorization stays owner-scoped
even though the scan is not.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_assistant.adapters.persistence.mapping import operation_row, to_operation
from health_assistant.adapters.persistence.schema import tool_operations
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.identifiers import OperationId, UserId
from health_assistant.domain.operations import OperationState, ToolOperation
from health_assistant.domain.scheduling import require_utc

_MUTABLE_COLUMNS = (
    "state",
    "approval_id",
    "attempts",
    "retry_budget",
    "lease_worker_id",
    "lease_acquired_at",
    "lease_expires_at",
    "external_ref",
    "last_error",
    "updated_at",
)


class SqlOperationRepository:
    """Operation persistence scoped to one transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save(self, operation: ToolOperation) -> None:
        """Store or advance an operation, refusing to touch another user's row."""
        statement = insert(tool_operations).values(operation_row(operation))
        result = await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=["operation_id"],
                set_={column: statement.excluded[column] for column in _MUTABLE_COLUMNS},
                where=tool_operations.c.owner_id == operation.owner_id,
            ).returning(tool_operations.c.operation_id)
        )
        if result.scalar_one_or_none() is None:
            raise OwnershipError(f"operation {operation.operation_id!r} belongs to another user")

    async def get(self, *, owner_id: UserId, operation_id: OperationId) -> ToolOperation | None:
        result = await self._connection.execute(
            select(tool_operations).where(
                tool_operations.c.operation_id == operation_id,
                tool_operations.c.owner_id == owner_id,
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else to_operation(dict(row))

    async def claim_next(self) -> ToolOperation | None:
        """Lock and return the oldest queued operation, skipping locked rows.

        `FOR UPDATE SKIP LOCKED` is what keeps two workers from taking the same
        row: the second skips it rather than blocking behind the first. The lock
        lasts until the surrounding transaction ends.
        """
        result = await self._connection.execute(
            select(tool_operations)
            .where(tool_operations.c.state == str(OperationState.QUEUED))
            .order_by(tool_operations.c.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = result.mappings().one_or_none()
        return None if row is None else to_operation(dict(row))

    async def expired_leases(self, *, now: datetime, limit: int = 50) -> tuple[ToolOperation, ...]:
        """Return executing operations whose lease has run out.

        An expired lease says a worker stopped reporting, not that the external
        write failed, so these are returned for reconciliation rather than being
        marked failed here.
        """
        instant = require_utc(now, "now")
        result = await self._connection.execute(
            select(tool_operations)
            .where(
                tool_operations.c.state == str(OperationState.EXECUTING),
                tool_operations.c.lease_expires_at <= instant,
            )
            .order_by(tool_operations.c.lease_expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return tuple(to_operation(dict(row)) for row in result.mappings())
