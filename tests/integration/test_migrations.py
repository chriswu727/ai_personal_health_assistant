"""The migration history and the declared schema must not drift apart."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import metadata
from tests.integration.conftest import downgrade_database, upgrade_database

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _compare(connection: Connection) -> list[object]:
    return list(compare_metadata(MigrationContext.configure(connection), metadata))


def _table_names(connection: Connection) -> list[str]:
    return [name for name in inspect(connection).get_table_names() if name != "alembic_version"]


async def _difference(engine: AsyncEngine) -> list[object]:
    async with engine.connect() as connection:
        return await connection.run_sync(_compare)


async def test_migrations_produce_the_declared_schema(engine: AsyncEngine) -> None:
    assert await _difference(engine) == []


async def test_the_initial_migration_is_reversible(engine: AsyncEngine, database_url: str) -> None:
    await asyncio.to_thread(downgrade_database, database_url, "base")
    async with engine.connect() as connection:
        remaining = await connection.run_sync(_table_names)
    assert remaining == []

    await asyncio.to_thread(upgrade_database, database_url)
    assert await _difference(engine) == []
