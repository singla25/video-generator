"""Migration 0002 adds the nullable templates.extra_slots column (DD-40, additive only).

Test IDs: MS-MG-* in docs/test-tree/multi-slot-model.md.
Runs on a throwaway ``vidgen_mig_*_test`` database, reset before and after each test. The name
guard refuses anything that does not end in ``_test``; ``vidgen`` is never touched.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from vidgen.infrastructure.db.models import Base
from vidgen.infrastructure.db.repositories import SqlTemplateRepository

ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = "0001"
TARGET = "0002"
TEMPLATE_0001_COLUMNS = {
    "id",
    "campaign_id",
    "video_key",
    "original_name",
    "duration_s",
    "width",
    "height",
    "slot_start_s",
    "slot_end_s",
    "slot_source",
    "slot_confidence",
    "slot_confirmed",
    "slot_error",
    "analysed_at",
    "face_region",
    "consent_confirmed",
    "created_at",
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
    """Drop everything; the schema is recreated empty."""
    assert (eng.url.database or "").endswith("_test")
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def alembic_config(url: str) -> Config:
    """Alembic config from backend/alembic.ini with the URL set programmatically."""
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def template_columns(eng: Engine) -> dict[str, dict[str, object]]:
    """Columns of the templates table by name."""
    return {c["name"]: dict(c) for c in inspect(eng).get_columns("templates")}


def insert_template_at_0001(eng: Engine) -> UUID:
    """A campaign and a template written with the 0001 columns only; returns the template id."""
    campaign_id, template_id = uuid4(), uuid4()
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO campaigns (id, name) VALUES (:id, 'old')"), {"id": campaign_id}
        )
        conn.execute(
            text(
                "INSERT INTO templates (id, campaign_id, video_key, original_name, duration_s, "
                "width, height, slot_start_s, slot_end_s, slot_source) VALUES (:id, :c, "
                "'templates/old.mp4', 'Krishan', 4.0, 320, 240, 1.0, 2.0, 'MANUAL')"
            ),
            {"id": template_id, "c": campaign_id},
        )
    return template_id


# ---- revision chain -------------------------------------------------------------------


def test_head_is_0002_and_it_follows_0001(migration_url: str) -> None:
    """MS-MG-P1."""
    script = ScriptDirectory.from_config(alembic_config(migration_url))
    assert script.get_current_head() == TARGET
    assert script.get_revision(TARGET).down_revision == PREVIOUS


# ---- upgrade --------------------------------------------------------------------------


def test_database_at_0001_has_no_extra_slots_column(engine: Engine, migration_url: str) -> None:
    """MS-MG-N1."""
    command.upgrade(alembic_config(migration_url), PREVIOUS)
    assert set(template_columns(engine)) == TEMPLATE_0001_COLUMNS


def test_upgrade_to_0002_adds_a_nullable_extra_slots_column(
    engine: Engine, migration_url: str
) -> None:
    """MS-MG-P2."""
    config = alembic_config(migration_url)
    command.upgrade(config, PREVIOUS)
    command.upgrade(config, TARGET)
    columns = template_columns(engine)
    assert "extra_slots" in columns
    assert columns["extra_slots"]["nullable"] is True


def test_migrated_schema_matches_the_models_exactly_at_0002(
    engine: Engine, migration_url: str
) -> None:
    """MS-MG-P3: no drift between migrations and models."""
    command.upgrade(alembic_config(migration_url), TARGET)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_rows_written_at_0001_stay_readable_after_the_upgrade(
    engine: Engine, migration_url: str
) -> None:
    """MS-MG-E1: old rows get NULL and read back as () with the other fields intact."""
    config = alembic_config(migration_url)
    command.upgrade(config, PREVIOUS)
    template_id = insert_template_at_0001(engine)
    command.upgrade(config, TARGET)
    with Session(engine) as session:
        loaded = SqlTemplateRepository(session).get(template_id)
    assert loaded is not None
    assert loaded.extra_slots == ()
    assert loaded.slot == (1.0, 2.0)
    assert loaded.original_name == "Krishan"


# ---- downgrade ------------------------------------------------------------------------


def test_downgrade_to_0001_drops_only_the_extra_slots_column(
    engine: Engine, migration_url: str
) -> None:
    """MS-MG-P4: the other columns and the rows survive."""
    config = alembic_config(migration_url)
    command.upgrade(config, PREVIOUS)
    template_id = insert_template_at_0001(engine)
    command.upgrade(config, TARGET)
    command.downgrade(config, PREVIOUS)
    assert set(template_columns(engine)) == TEMPLATE_0001_COLUMNS
    with engine.connect() as conn:
        kept = conn.execute(
            text("SELECT original_name FROM templates WHERE id = :id"), {"id": template_id}
        ).scalar_one()
    assert kept == "Krishan"


def test_upgrade_downgrade_upgrade_round_trip_matches_the_models(
    engine: Engine, migration_url: str
) -> None:
    """MS-MG-E2."""
    config = alembic_config(migration_url)
    command.upgrade(config, TARGET)
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, TARGET)
    assert "extra_slots" in template_columns(engine)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_the_migration_only_runs_against_a_throwaway_test_database(migration_url: str) -> None:
    """MS-MG-E3: safety guard for this module."""
    name = make_url(migration_url).database or ""
    assert name.endswith("_test")
    assert name != "vidgen"
