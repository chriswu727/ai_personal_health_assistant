"""Fixtures for the database-backed tests.

These tests are skipped only when no database URL is configured. Once one is
set, a connection or migration failure is an error rather than a skip, so a
misconfigured run cannot look like a passing one.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import create_database_engine

URL_VARIABLE = "HEALTH_ASSISTANT_TEST_DATABASE_URL"
OWNED_TABLES = "plan_items, plan_versions, plans, users"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Migrate up.

    Alembic's environment drives an async engine through ``asyncio.run``, which
    cannot be called while a loop is already running. Async callers must reach
    this through ``asyncio.to_thread``.
    """
    command.upgrade(alembic_config(database_url), revision)


def downgrade_database(database_url: str, revision: str) -> None:
    """Migrate down, with the same threading requirement as ``upgrade_database``."""
    command.downgrade(alembic_config(database_url), revision)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(URL_VARIABLE)
    if not url:
        pytest.skip(f"{URL_VARIABLE} is not set")
    return url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    upgrade_database(database_url)
    return database_url


@pytest_asyncio.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(migrated_database)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {OWNED_TABLES} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()
