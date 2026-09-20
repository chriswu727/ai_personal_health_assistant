"""Engine construction and the transactional boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, create_engine

from health_assistant.adapters.persistence.plans import SqlPlanRepository
from health_assistant.adapters.persistence.users import SqlUserRepository


def create_database_engine(url: str) -> Engine:
    """Return an engine whose sessions report timestamps in UTC."""
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


@dataclass(frozen=True, slots=True)
class SqlUnitOfWork:
    """The repositories spanning one transaction."""

    connection: Connection

    @property
    def plans(self) -> SqlPlanRepository:
        return SqlPlanRepository(self.connection)

    @property
    def users(self) -> SqlUserRepository:
        return SqlUserRepository(self.connection)


@contextmanager
def unit_of_work(engine: Engine) -> Iterator[SqlUnitOfWork]:
    """Run a block inside one transaction, committing only if it returns."""
    with engine.begin() as connection:
        yield SqlUnitOfWork(connection=connection)
