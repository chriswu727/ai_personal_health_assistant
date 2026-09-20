"""Engine construction and the transactional boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from health_assistant.adapters.persistence.plans import SqlPlanRepository
from health_assistant.adapters.persistence.users import SqlUserRepository


def create_database_engine(url: str) -> AsyncEngine:
    """Return an engine whose sessions report timestamps in UTC."""
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


@dataclass(frozen=True, slots=True)
class SqlUnitOfWork:
    """The repositories spanning one transaction."""

    connection: AsyncConnection

    @property
    def plans(self) -> SqlPlanRepository:
        return SqlPlanRepository(self.connection)

    @property
    def users(self) -> SqlUserRepository:
        return SqlUserRepository(self.connection)


@asynccontextmanager
async def unit_of_work(engine: AsyncEngine) -> AsyncIterator[SqlUnitOfWork]:
    """Run a block inside one transaction, committing only if it returns."""
    async with engine.begin() as connection:
        yield SqlUnitOfWork(connection=connection)
