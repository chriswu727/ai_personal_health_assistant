"""Approval storage.

An approval's scope never changes once granted: a different scope is a different
confirmation. Only revocation mutates a stored approval, so the approved actions
are written once and the approval row carries the revocation instant.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_assistant.adapters.persistence.mapping import (
    approval_action_rows,
    approval_row,
    to_approval,
)
from health_assistant.adapters.persistence.schema import approval_actions, approvals
from health_assistant.domain.approvals import Approval
from health_assistant.domain.errors import OwnershipError
from health_assistant.domain.identifiers import ApprovalId, UserId


class SqlApprovalRepository:
    """Approval persistence scoped to one transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save(self, approval: Approval) -> None:
        row = approval_row(approval)
        statement = insert(approvals).values(row)
        result = await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=["approval_id"],
                set_={"revoked_at": statement.excluded["revoked_at"]},
                where=approvals.c.owner_id == approval.owner_id,
            ).returning(approvals.c.approval_id)
        )
        if result.scalar_one_or_none() is None:
            raise OwnershipError(f"approval {approval.approval_id!r} belongs to another user")

        actions = approval_action_rows(approval)
        await self._connection.execute(
            insert(approval_actions)
            .values(actions)
            .on_conflict_do_nothing(
                index_elements=["approval_id", "item_id", "kind", "compensates"]
            )
        )

    async def get(self, *, owner_id: UserId, approval_id: ApprovalId) -> Approval | None:
        result = await self._connection.execute(
            select(approvals).where(
                approvals.c.approval_id == approval_id,
                approvals.c.owner_id == owner_id,
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        actions = await self._connection.execute(
            select(approval_actions).where(approval_actions.c.approval_id == approval_id)
        )
        return to_approval(dict(row), [dict(action) for action in actions.mappings()])
