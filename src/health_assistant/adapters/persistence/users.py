"""Minimal user records.

Identity provider integration belongs to a later sprint. What is needed now is a
row that user-owned tables can reference, so that a plan cannot be written for a
user who does not exist.
"""

from datetime import datetime

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from health_assistant.adapters.persistence.schema import users
from health_assistant.domain.identifiers import UserId, require_identifier
from health_assistant.domain.scheduling import require_time_zone, require_utc


class SqlUserRepository:
    """User persistence scoped to one transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def ensure(self, *, user_id: UserId, time_zone: str, created_at: datetime) -> None:
        """Create the user if absent, leaving an existing record untouched."""
        self._connection.execute(
            insert(users)
            .values(
                user_id=require_identifier(user_id, "user_id"),
                time_zone=require_time_zone(time_zone),
                created_at=require_utc(created_at, "created_at"),
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )

    def exists(self, user_id: UserId) -> bool:
        found = self._connection.execute(
            select(users.c.user_id).where(users.c.user_id == user_id)
        ).scalar_one_or_none()
        return found is not None
