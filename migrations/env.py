"""Alembic entry point.

The database URL comes from the Alembic config when a caller sets it, and from
``HEALTH_ASSISTANT_DATABASE_URL`` otherwise. It is never committed.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from health_assistant.adapters.persistence.schema import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

URL_VARIABLE = "HEALTH_ASSISTANT_DATABASE_URL"


def database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    url = configured or os.environ.get(URL_VARIABLE)
    if not url:
        message = f"set {URL_VARIABLE} to the database to migrate"
        raise RuntimeError(message)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    """Run the migrations against an already-open synchronous connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
