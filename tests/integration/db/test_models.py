"""Database models: tables, campaign_id everywhere, column shapes (ADR-003, D6, C5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, LargeBinary, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.integration.db.helpers import make_campaign, make_template
from vidgen.infrastructure.db.models import (
    AuditLog,
    Base,
    Batch,
    BatchRow,
    ConsentRecord,
    Template,
)

EXPECTED_TABLES = {
    "campaigns",
    "templates",
    "consent_records",
    "batches",
    "batch_rows",
    "audit_log",
    "login_attempts",
}


def test_all_expected_tables_are_defined() -> None:
    """Plan T10: campaigns, templates, consent, batches, rows, audit_log."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_except_campaigns_has_a_required_campaign_id() -> None:
    """D6: the data model carries campaign_id for later multi-user."""
    for name, table in Base.metadata.tables.items():
        if name == "campaigns":
            continue
        column = table.c.campaign_id
        assert not column.nullable, name
        targets = {fk.target_fullname for fk in column.foreign_keys}
        assert targets == {"campaigns.id"}, name


def test_tables_exist_in_the_test_database(db: Engine) -> None:
    """The test DB was built from the models (no Alembic)."""
    assert set(inspect(db).get_table_names()) >= EXPECTED_TABLES


def test_batch_rows_store_personal_data_only_as_binary_ciphertext() -> None:
    """C5: no plaintext name/ID columns exist; encrypted columns are binary."""
    columns = Base.metadata.tables["batch_rows"].c
    for forbidden in ("name", "spoken_name", "voter_id", "id_number"):
        assert forbidden not in columns
    for encrypted in ("name_enc", "spoken_name_enc", "voter_id_enc"):
        assert isinstance(columns[encrypted].type, LargeBinary)
    assert "voter_id_index" in columns
    assert "key_id" in columns


def test_template_profile_and_consent_fields_round_trip(db: Engine) -> None:
    """AC6-P3 / AC5-P3: profile (slot, confidence, manual flag, face region, consent) persists."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        template.slot_start_s = 1.0
        template.slot_end_s = 1.6
        template.slot_source = "AUTO"
        template.slot_confidence = 0.93
        template.slot_confirmed = True
        template.face_region = {"x": 0, "y": 0, "w": 0, "h": 0}
        template.consent_confirmed = True
        session.add(
            ConsentRecord(
                campaign_id=campaign.id,
                template_id=template.id,
                file_key="consent/c.pdf",
                content_type="application/pdf",
                confirmed=True,
            )
        )
        session.commit()
        template_id = template.id
    with Session(db) as session:
        loaded = session.get(Template, template_id)
        assert loaded is not None
        assert (loaded.slot_start_s, loaded.slot_end_s) == (1.0, 1.6)
        assert loaded.original_name == "Krishan"
        assert loaded.slot_source == "AUTO"
        assert loaded.slot_confidence == pytest.approx(0.93)
        assert loaded.slot_confirmed is True
        assert loaded.consent_confirmed is True
        assert loaded.face_region == {"x": 0, "y": 0, "w": 0, "h": 0}


def test_new_template_defaults_to_unconfirmed_without_consent(db: Engine) -> None:
    """AC5-N1: a fresh template is not usable."""
    with Session(db) as session:
        template = make_template(session, make_campaign(session))
        session.commit()
        assert template.slot_confirmed is False
        assert template.consent_confirmed is False
        assert template.slot_start_s is None


def test_rows_with_an_unknown_campaign_are_rejected(db: Engine) -> None:
    """D6: campaign_id is enforced by a foreign key."""
    with Session(db) as session:
        session.add(
            Template(
                campaign_id=uuid.uuid4(),
                video_key="x.mp4",
                original_name="Krishan",
                duration_s=1.0,
                width=1,
                height=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_deleting_a_batch_cascades_to_its_rows(db: Engine) -> None:
    """AC17-P5 (database side): rows disappear with their batch."""
    with Session(db) as session:
        campaign = make_campaign(session)
        template = make_template(session, campaign)
        batch = Batch(campaign_id=campaign.id, template_id=template.id, status="DRAFT")
        session.add(batch)
        session.flush()
        session.add(
            BatchRow(
                campaign_id=campaign.id,
                batch_id=batch.id,
                row_number=2,
                status="QUEUED",
                name_enc=b"x",
                voter_id_enc=b"y",
                voter_id_index="abc",
                key_id="k1",
            )
        )
        session.commit()
        session.delete(batch)
        session.commit()
        assert session.query(BatchRow).count() == 0


def test_audit_log_row_holds_actor_action_time_and_details(db: Engine) -> None:
    """C4."""
    with Session(db) as session:
        campaign = make_campaign(session)
        session.add(
            AuditLog(
                campaign_id=campaign.id,
                at=datetime(2026, 10, 18, 9, 0, tzinfo=UTC),
                actor="admin",
                action="TEMPLATE_UPLOADED",
                details={"template_id": "t1"},
            )
        )
        session.commit()
        entry = session.query(AuditLog).one()
        assert (entry.actor, entry.action, entry.details) == (
            "admin",
            "TEMPLATE_UPLOADED",
            {"template_id": "t1"},
        )
        assert entry.at.tzinfo is not None
