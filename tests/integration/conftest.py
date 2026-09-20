"""Fixtures for the database-backed tests.

These tests are skipped only when no database URL is configured. Once one is
set, a connection or migration failure is an error rather than a skip, so a
misconfigured run cannot look like a passing one.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from health_assistant.adapters.persistence import create_database_engine

URL_VARIABLE = "HEALTH_ASSISTANT_TEST_DATABASE_URL"
OWNED_TABLES = "plan_items, plan_versions, plans, users"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(URL_VARIABLE)
    if not url:
        pytest.skip(f"{URL_VARIABLE} is not set")
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(database_url), "head")
    engine = create_database_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Iterator[None]:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {OWNED_TABLES} RESTART IDENTITY CASCADE"))
    yield
