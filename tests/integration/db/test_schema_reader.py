"""BL-8 SS-R*: the read-only adapter vidgen.infrastructure.db.schema_reader.

Runs only on the throwaway ``vidgen_mig_*_test`` database (never a protected one).
Adapter contract: ``SqlSchemaVersionReader(engine)`` with ``current_revision()`` (a SELECT on
alembic_version; no table or no row -> None) and ``expected_revision()`` (alembic head of
backend/migrations). It never runs DDL or migrations; connection errors propagate.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from tests.integration.db.test_migration_0002_extra_slots import _reset, alembic_config
from vidgen.infrastructure.db.schema_reader import SqlSchemaVersionReader


@pytest.fixture
def engine(migration_db_url: str) -> Iterator[Engine]:
    assert (make_url(migration_db_url).database or "").endswith("_test")
    eng = create_engine(migration_db_url)
    _reset(eng)
    yield eng
    _reset(eng)
    eng.dispose()


def head(url: str) -> str:
    found = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
    assert found is not None
    return found


def _version(eng: Engine) -> list[str]:
    with eng.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))]


@pytest.mark.parametrize("revision", ["0001", "0002"])
def test_reads_an_older_revision(engine: Engine, migration_db_url: str, revision: str) -> None:
    """SS-R-P1: the database at an older revision reports it, expected is the shipped head."""
    command.upgrade(alembic_config(migration_db_url), revision)
    reader = SqlSchemaVersionReader(engine)
    assert reader.current_revision() == revision
    assert reader.expected_revision() == head(migration_db_url)


def test_reads_the_head_revision(engine: Engine, migration_db_url: str) -> None:
    """SS-R-P2."""
    command.upgrade(alembic_config(migration_db_url), "head")
    reader = SqlSchemaVersionReader(engine)
    assert reader.current_revision() == reader.expected_revision() == head(migration_db_url)


def test_expected_revision_is_at_least_0003(engine: Engine) -> None:
    """SS-R-P3: expected comes from the shipped scripts, not from the database."""
    assert SqlSchemaVersionReader(engine).expected_revision() >= "0003"


def test_missing_alembic_version_table_gives_none(engine: Engine) -> None:
    """SS-R-E1: a brand new empty database: None, no error, and nothing gets created."""
    assert SqlSchemaVersionReader(engine).current_revision() is None
    assert "alembic_version" not in inspect(engine).get_table_names()


def test_empty_alembic_version_table_gives_none(engine: Engine) -> None:
    """SS-R-E2: the table exists but has no row."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32) NOT NULL)"))
    assert SqlSchemaVersionReader(engine).current_revision() is None


def test_reading_is_read_only(engine: Engine, migration_db_url: str) -> None:
    """SS-R-N1: reading changes nothing (table list and version row identical before/after)."""
    command.upgrade(alembic_config(migration_db_url), "0002")
    before = (sorted(inspect(engine).get_table_names()), _version(engine))
    reader = SqlSchemaVersionReader(engine)
    reader.current_revision()
    reader.expected_revision()
    assert (sorted(inspect(engine).get_table_names()), _version(engine)) == before


def test_connection_error_propagates_as_a_db_error() -> None:
    """SS-R-N2: an unreachable database raises the SQLAlchemy connection error (not None)."""
    dead = create_engine(
        "postgresql+psycopg://nobody:pw@127.0.0.1:1/x_test", connect_args={"connect_timeout": 1}
    )
    with pytest.raises(OperationalError):
        SqlSchemaVersionReader(dead).current_revision()
