"""Migration 0003 adds provider_id, data_class and cost_usd (render providers, additive only).

Test IDs: RP-MIG-* in docs/test-tree/render-providers.md. Created, never run on the dev database:
every test runs on the throwaway ``vidgen_mig_*_test`` database (name guard below).
Revision 0003 must follow 0002 and add:
  batches.provider_id    text, nullable (null = default provider)
  batches.data_class     text, NOT NULL, server default 'real'
  batch_rows.cost_usd    numeric, nullable
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.integration.db.test_migration_0002_extra_slots import _reset, alembic_config
from vidgen.infrastructure.db.models import Base

PREVIOUS = "0002"
TARGET = "0003"


@pytest.fixture(scope="module")
def migration_url(migration_db_url: str) -> str:
    assert (make_url(migration_db_url).database or "").endswith("_test")
    return migration_db_url


@pytest.fixture
def engine(migration_url: str) -> Iterator[Engine]:
    eng = create_engine(migration_url)
    _reset(eng)
    yield eng
    _reset(eng)
    eng.dispose()


def columns(eng: Engine, table: str) -> dict[str, dict[str, object]]:
    return {c["name"]: dict(c) for c in inspect(eng).get_columns(table)}


def insert_batch_at_0002(eng: Engine) -> UUID:
    """A campaign, template, batch and row written with the 0002 columns only."""
    campaign_id, template_id, batch_id = uuid4(), uuid4(), uuid4()
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
        conn.execute(
            text("INSERT INTO batches (id, campaign_id, template_id) VALUES (:b, :c, :t)"),
            {"b": batch_id, "c": campaign_id, "t": template_id},
        )
    return batch_id


def test_head_is_0003_and_it_follows_0002(migration_url: str) -> None:
    """RP-MIG-P1."""
    script = ScriptDirectory.from_config(alembic_config(migration_url))
    assert script.get_current_head() == TARGET
    assert script.get_revision(TARGET).down_revision == PREVIOUS


def test_database_at_0002_has_none_of_the_new_columns(engine: Engine, migration_url: str) -> None:
    """RP-MIG-N1."""
    command.upgrade(alembic_config(migration_url), PREVIOUS)
    batches, rows = columns(engine, "batches"), columns(engine, "batch_rows")
    assert not {"provider_id", "data_class"} & set(batches)
    assert "cost_usd" not in rows


def test_upgrade_adds_the_three_columns_with_the_planned_nullability(
    engine: Engine, migration_url: str
) -> None:
    """RP-MIG-P2."""
    command.upgrade(alembic_config(migration_url), TARGET)
    batches, rows = columns(engine, "batches"), columns(engine, "batch_rows")
    assert batches["provider_id"]["nullable"] is True
    assert batches["data_class"]["nullable"] is False
    assert "real" in str(batches["data_class"]["default"])
    assert rows["cost_usd"]["nullable"] is True


def test_migrated_schema_matches_the_models_exactly_at_0003(
    engine: Engine, migration_url: str
) -> None:
    """RP-MIG-P3: no drift between migrations and models."""
    command.upgrade(alembic_config(migration_url), TARGET)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_an_old_batch_survives_the_upgrade_as_real_data_with_no_provider(
    engine: Engine, migration_url: str
) -> None:
    """RP-MIG-E1 (R5)."""
    config = alembic_config(migration_url)
    command.upgrade(config, PREVIOUS)
    batch_id = insert_batch_at_0002(engine)
    command.upgrade(config, TARGET)
    with engine.connect() as conn:
        provider, data_class = conn.execute(
            text("SELECT provider_id, data_class FROM batches WHERE id = :id"), {"id": batch_id}
        ).one()
    assert (provider, data_class) == (None, "real")


def test_downgrade_removes_only_the_three_columns_and_keeps_the_batch(
    engine: Engine, migration_url: str
) -> None:
    """RP-MIG-P4."""
    config = alembic_config(migration_url)
    command.upgrade(config, PREVIOUS)
    batch_id = insert_batch_at_0002(engine)
    command.upgrade(config, TARGET)
    command.downgrade(config, PREVIOUS)
    assert not {"provider_id", "data_class"} & set(columns(engine, "batches"))
    assert "cost_usd" not in columns(engine, "batch_rows")
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM batches WHERE id = :id"), {"id": batch_id}
            ).scalar_one()
            == 1
        )


def test_upgrade_downgrade_upgrade_round_trip_matches_the_models(
    engine: Engine, migration_url: str
) -> None:
    """RP-MIG-E2."""
    config = alembic_config(migration_url)
    command.upgrade(config, TARGET)
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, TARGET)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_the_migration_only_runs_against_a_throwaway_test_database(migration_url: str) -> None:
    """RP-MIG-E3: safety guard; neither vidgen nor vidgen_demo is ever used."""
    name = make_url(migration_url).database or ""
    assert name.endswith("_test")
    assert name not in {"vidgen", "vidgen_demo"}
