"""Shared fixtures for integration tests that need the throwaway Postgres database.

The database name must end in ``_test``; the dev database ``vidgen`` is never touched.
Tables are created from the models (no Alembic) and truncated before every test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

DEFAULT_TEST_URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_test"


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """URL of the throwaway database (env ``VIDGEN_TEST_DATABASE_URL`` or the compose default)."""
    url = os.environ.get("VIDGEN_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    database = make_url(url).database or ""
    assert database.endswith("_test"), (
        f"refusing to use database '{database}': name must end in _test"
    )
    return url


def _ensure_database(url: str) -> None:
    """Create the test database if it is missing (connects to the server's 'postgres' db)."""
    parsed = make_url(url)
    admin = parsed.set(database="postgres", drivername="postgresql")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (parsed.database,))
        if exists.fetchone() is None:
            conn.execute(f'CREATE DATABASE "{parsed.database}"')


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
