"""Alembic entry point.

The database URL comes from the Alembic config when a caller sets it, and from
``HEALTH_ASSISTANT_DATABASE_URL`` otherwise. It is never committed.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

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


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
