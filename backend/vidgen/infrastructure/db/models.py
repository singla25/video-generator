"""SQLAlchemy 2 models (ADR-003). Personal data is stored only as ciphertext (C5, ADR-005).

Every table except ``campaigns`` carries a required ``campaign_id`` (D6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonDict = JSON().with_variant(JSONB(), "postgresql")
TIMESTAMP = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Declarative base with a fixed constraint naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _campaign_id() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("campaigns.id"), nullable=False)


def _created_at() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)


class Campaign(Base):
    """A campaign groups templates and batches; one default campaign exists in M1."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()


class Template(Base):
    """A reusable template video with its analysed profile (AC6)."""

    __tablename__ = "templates"
    __table_args__ = (Index("ix_templates_campaign_id", "campaign_id"),)

    id: Mapped[uuid.UUID] = _id()
    campaign_id: Mapped[uuid.UUID] = _campaign_id()
    video_key: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(200))
    duration_s: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    slot_start_s: Mapped[float | None] = mapped_column(Float)
    slot_end_s: Mapped[float | None] = mapped_column(Float)
    slot_source: Mapped[str | None] = mapped_column(String(16))
    slot_confidence: Mapped[float | None] = mapped_column(Float)
    slot_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    slot_error: Mapped[str | None] = mapped_column(String(64))
    analysed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    face_region: Mapped[dict[str, Any] | None] = mapped_column(JsonDict)
    consent_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _created_at()


class ConsentRecord(Base):
    """One uploaded consent file; replacing consent adds a record and keeps the old one."""

    __tablename__ = "consent_records"
    __table_args__ = (Index("ix_consent_records_template_id", "template_id"),)

    id: Mapped[uuid.UUID] = _id()
    campaign_id: Mapped[uuid.UUID] = _campaign_id()
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("templates.id", ondelete="CASCADE")
    )
    file_key: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    confirmed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _created_at()


class Batch(Base):
    """A run of one template over one sheet."""

    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_batches_idempotency_key"),
        Index("ix_batches_campaign_id_status", "campaign_id", "status"),
        Index("ix_batches_template_id", "template_id"),
        Index("ix_batches_finished_at", "finished_at"),  # retention job (D-17)
    )

    id: Mapped[uuid.UUID] = _id()
    campaign_id: Mapped[uuid.UUID] = _campaign_id()
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("templates.id"))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", server_default="DRAFT")
    sheet_key: Mapped[str | None] = mapped_column(String(500))
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(JsonDict)
    folder_name: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class BatchRow(Base):
    """One sheet row. Name, spoken name and voter ID exist only as ciphertext (C5)."""

    __tablename__ = "batch_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_batch_rows_batch_id_row_number"),
        Index("ix_batch_rows_batch_id_status", "batch_id", "status"),
        Index("ix_batch_rows_batch_id_voter_id_index", "batch_id", "voter_id_index"),
        # Two renderable rows may never share an ID; SKIPPED rows (invalid or duplicate rows
        # kept for the manifest) are exempt (D-17).
        Index(
            "uq_batch_rows_batch_id_voter_id_index_live",
            "batch_id",
            "voter_id_index",
            unique=True,
            postgresql_where=text("status <> 'SKIPPED'"),
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    campaign_id: Mapped[uuid.UUID] = _campaign_id()
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("batches.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    name_enc: Mapped[bytes] = mapped_column(LargeBinary)
    spoken_name_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    voter_id_enc: Mapped[bytes] = mapped_column(LargeBinary)
    voter_id_index: Mapped[str] = mapped_column(String(64))
    key_id: Mapped[str] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    output_key: Mapped[str | None] = mapped_column(String(500))
    render_seconds: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class AuditLog(Base):
    """Append-only audit trail. Details never hold personal data (C4, C5)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_campaign_id_at", "campaign_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[uuid.UUID] = _campaign_id()
    at: Mapped[datetime] = mapped_column(TIMESTAMP)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)


class LoginAttempt(Base):
    """Shared login-protection state (D-15, D-17): one row per client plus one global row.

    ``client_key`` is the resolved IP address or the GLOBAL_KEY sentinel; ``locked_until`` is a
    lock for a client and the throttle end for the global row. No passwords or personal data.
    """

    __tablename__ = "login_attempts"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("campaigns.id"), primary_key=True
    )
    client_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_allowed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


__all__ = [
    "AuditLog",
    "Base",
    "Batch",
    "BatchRow",
    "Campaign",
    "ConsentRecord",
    "LoginAttempt",
    "Template",
]
