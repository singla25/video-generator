"""Alembic migrations against a separate throwaway database (plan D-14).

Uses a per-session database ``vidgen_mig_<hex>_test`` created and removed by the conftest. The
name must end in ``_test``; ``vidgen``, ``vidgen_test`` and ``vidgen_migration_test`` are untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from vidgen.infrastructure.db.models import Base

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_TABLES = {
    "campaigns",
    "templates",
    "consent_records",
    "batches",
    "batch_rows",
    "audit_log",
}


@pytest.fixture(scope="module")
def migration_url(migration_db_url: str) -> str:
    """URL of this session's migration database (created and removed by the conftest)."""
    assert (make_url(migration_db_url).database or "").endswith("_test")
    return migration_db_url


@pytest.fixture
def engine(migration_url: str) -> Iterator[Engine]:
    """Engine on the migration database, emptied before and after each test."""
    eng = create_engine(migration_url)
    _reset(eng)
    yield eng
    _reset(eng)
    eng.dispose()


def _reset(eng: Engine) -> None:
    """Remove every table (the schema is recreated empty)."""
    assert (eng.url.database or "").endswith("_test")
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def alembic_config(url: str) -> Config:
    """Alembic config from backend/alembic.ini with the database URL set programmatically."""
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def tables(eng: Engine) -> set[str]:
    """Table names currently in the database."""
    return set(inspect(eng).get_table_names())


# ---- upgrade --------------------------------------------------------------------------


def test_upgrade_head_creates_the_expected_tables(engine: Engine, migration_url: str) -> None:
    """D-14: the six app tables (and alembic_version) exist."""
    command.upgrade(alembic_config(migration_url), "head")
    assert tables(engine) >= EXPECTED_TABLES | {"alembic_version"}


def test_migrated_schema_matches_the_models_exactly(engine: Engine, migration_url: str) -> None:
    """Autogenerate finds no difference between the migrations and Base.metadata."""
    command.upgrade(alembic_config(migration_url), "head")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_every_table_except_campaigns_has_a_campaign_id_after_migration(
    engine: Engine, migration_url: str
) -> None:
    """D6, checked on the migrated database rather than on the models."""
    command.upgrade(alembic_config(migration_url), "head")
    inspector = inspect(engine)
    for name in tables(engine) - {"campaigns", "alembic_version"}:
        columns = {c["name"]: c for c in inspector.get_columns(name)}
        assert "campaign_id" in columns, name
        assert columns["campaign_id"]["nullable"] is False, name


def test_migrated_batch_rows_hold_no_plaintext_personal_data_columns(
    engine: Engine, migration_url: str
) -> None:
    """C5: only encrypted bytes and the keyed index exist."""
    command.upgrade(alembic_config(migration_url), "head")
    columns = {c["name"]: c for c in inspect(engine).get_columns("batch_rows")}
    for forbidden in ("name", "voter_id", "spoken_name", "id_number"):
        assert forbidden not in columns
    for encrypted in ("name_enc", "spoken_name_enc", "voter_id_enc"):
        assert "BYTEA" in str(columns[encrypted]["type"]).upper()
    assert "voter_id_index" in columns
    assert "key_id" in columns


def test_the_duplicate_guard_exists_after_migration(engine: Engine, migration_url: str) -> None:
    """A partial unique index on (batch_id, voter_id_index) excluding SKIPPED rows."""
    command.upgrade(alembic_config(migration_url), "head")
    with engine.connect() as connection:
        definitions = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'batch_rows'")
        ).scalars()
        unique = [d for d in definitions if "UNIQUE" in d.upper() and "voter_id_index" in d]
    assert unique, "no unique index on voter_id_index"
    assert any("SKIPPED" in d.upper() and "WHERE" in d.upper() for d in unique)


def test_upgrade_head_twice_is_harmless(engine: Engine, migration_url: str) -> None:
    """Already at head: nothing to do, nothing breaks."""
    config = alembic_config(migration_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert tables(engine) >= EXPECTED_TABLES


# ---- downgrade ------------------------------------------------------------------------


def test_downgrade_base_removes_every_app_table(engine: Engine, migration_url: str) -> None:
    """D-14: downgrade drops exactly what upgrade created."""
    config = alembic_config(migration_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert tables(engine) <= {"alembic_version"}


def test_upgrade_works_again_after_a_full_downgrade(engine: Engine, migration_url: str) -> None:
    """Round trip: head -> base -> head."""
    config = alembic_config(migration_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert tables(engine) >= EXPECTED_TABLES
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_migration_never_touches_the_dev_or_model_test_databases(
    migration_url: str, test_db_url: str
) -> None:
    """Safety guard for this test module."""
    assert (make_url(migration_url).database or "").startswith("vidgen_mig_")
    assert make_url(migration_url).database != "vidgen"
    assert make_url(migration_url).database != make_url(test_db_url).database
