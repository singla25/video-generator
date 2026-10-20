"""Shared fixtures for integration tests that need the throwaway Postgres database.

Every pytest session creates its own databases ``vidgen_<8 hex>_test`` (models) and
``vidgen_mig_<8 hex>_test`` (migrations) and removes them at the end, even after failures, so
parallel runs by several agents cannot interfere. Only this session's databases are removed.
``VIDGEN_TEST_DATABASE_URL`` overrides the model database (then it is kept); the name must end in
``_test``. The databases ``vidgen``, ``vidgen_test`` and ``vidgen_migration_test`` are never
created or removed here. Tables are created from the models and truncated before every test.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

SERVER_URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/postgres"
PROTECTED = frozenset({"vidgen", "vidgen_test", "vidgen_migration_test", "postgres"})
LEGACY_MIGRATION_DB = "vidgen_migration_test"
OVERRIDE_ENV = "VIDGEN_TEST_DATABASE_URL"


def _random_name(prefix: str) -> str:
    """A unique database name for this session, e.g. ``vidgen_1a2b3c4d_test``."""
    return f"{prefix}_{secrets.token_hex(4)}_test"


def _admin_dsn(url: str) -> str:
    """Connection string to the server's maintenance database."""
    admin = make_url(url).set(database="postgres", drivername="postgresql")
    return admin.render_as_string(hide_password=False)


def _remove_database(url: str) -> None:
    """Remove one database this session created; refuses protected or non-test names."""
    name = make_url(url).database or ""
    assert name.endswith("_test") and name not in PROTECTED, f"refusing to remove '{name}'"
    with psycopg.connect(_admin_dsn(url), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _ensure_database(url: str) -> None:
    """Create the test database if it is missing (connects to the server's 'postgres' db)."""
    name = make_url(url).database
    with psycopg.connect(_admin_dsn(url), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if exists.fetchone() is None:
            conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session")
def test_db_url(request: pytest.FixtureRequest) -> str:
    """URL of this session's throwaway database (``VIDGEN_TEST_DATABASE_URL`` overrides)."""
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        database = make_url(override).database or ""
        assert database.endswith("_test"), (
            f"refusing to use database '{database}': name must end in _test"
        )
        return override
    base = make_url(SERVER_URL).set(database=_random_name("vidgen"))
    url = base.render_as_string(hide_password=False)
    # Register the cleanup first so a failure while creating still removes a partial database.
    request.addfinalizer(lambda: _remove_database(url))
    _ensure_database(url)
    return url


@pytest.fixture(scope="session")
def migration_db_url(test_db_url: str, request: pytest.FixtureRequest) -> str:
    """URL of this session's migration database (removed at the end unless overridden)."""
    owned = not os.environ.get(OVERRIDE_ENV)
    name = _random_name("vidgen_mig") if owned else LEGACY_MIGRATION_DB
    assert name.endswith("_test")
    url = make_url(test_db_url).set(database=name).render_as_string(hide_password=False)
    if owned:
        request.addfinalizer(lambda: _remove_database(url))
    _ensure_database(url)
    return url


@pytest.fixture(scope="session")
def db_engine(test_db_url: str) -> Iterator[Engine]:
    """Engine on the test database with all tables created from the models."""
    from vidgen.infrastructure.db.models import Base

    _ensure_database(test_db_url)
    engine = create_engine(test_db_url, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Engine:
    """The test engine with every table emptied first (fast isolation between tests)."""
    from vidgen.infrastructure.db.models import Base

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    return db_engine
