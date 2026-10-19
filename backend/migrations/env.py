"""Alembic environment.

It needs only a database URL: no application settings and no secrets. The URL is taken, in
order, from ``-x db_url=...``, from ``sqlalchemy.url`` on the Alembic config (set
programmatically or in alembic.ini), or from the ``VIDGEN_DATABASE_URL`` environment variable.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from vidgen.infrastructure.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
URL_ENV_VAR = "VIDGEN_DATABASE_URL"


def database_url() -> str:
    """The URL to migrate; fails with a clear message when none is given."""
    url = (
        context.get_x_argument(as_dictionary=True).get("db_url")
        or config.get_main_option("sqlalchemy.url")
        or os.environ.get(URL_ENV_VAR)
    )
    if not url:
        raise RuntimeError(f"No database URL: set {URL_ENV_VAR} or pass -x db_url=...")
    return url


def run_migrations_offline() -> None:
    """Emit SQL without connecting to the database."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
