"""The migration history and the declared schema must not drift apart."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from health_assistant.adapters.persistence import metadata
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration


def _difference(engine: Engine) -> list[object]:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return list(compare_metadata(context, metadata))


def test_migrations_produce_the_declared_schema(engine: Engine) -> None:
    assert _difference(engine) == []


def test_the_initial_migration_is_reversible(engine: Engine, database_url: str) -> None:
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    with engine.connect() as connection:
        remaining = inspect(connection).get_table_names()
    assert [name for name in remaining if name != "alembic_version"] == []

    command.upgrade(config, "head")
    assert _difference(engine) == []
