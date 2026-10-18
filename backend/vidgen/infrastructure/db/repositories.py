"""SQLAlchemy repositories (ADR-003). Personal data is encrypted on the way in (ADR-005)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from vidgen.infrastructure.db.models import (
    AuditLog,
    Batch,
    BatchRow,
    Campaign,
    ConsentRecord,
    Template,
)
from vidgen.ports.models import AuditEntry, TemplateRecord

if TYPE_CHECKING:
    from vidgen.ports import Cipher

DEFAULT_CAMPAIGN_NAME = "default"
# A fixed id keeps "create the default campaign" race-free without a unique name.
DEFAULT_CAMPAIGN_ID = UUID("00000000-0000-4000-8000-0000000000c1")
_TEMPLATE_FIELDS = (
    "video_key", "original_name", "duration_s", "width", "height", "slot_start_s",
    "slot_end_s", "slot_source", "slot_confidence", "slot_confirmed", "slot_error",
    "analysed_at", "consent_confirmed",
)  # fmt: skip


def ensure_default_campaign(session: Session) -> UUID:
    """Return the id of the single default campaign, creating it on first use (D6)."""
    statement = (
        pg_insert(Campaign)
        .values(id=DEFAULT_CAMPAIGN_ID, name=DEFAULT_CAMPAIGN_NAME)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    session.execute(statement)
    return DEFAULT_CAMPAIGN_ID


def _to_record(row: Template) -> TemplateRecord:
    """Map a Template ORM row to the plain record the services use."""
    return TemplateRecord(
        id=row.id, created_at=row.created_at, **{f: getattr(row, f) for f in _TEMPLATE_FIELDS}
    )


class SqlTemplateRepository:
    """Templates and consent records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, template_id: UUID) -> TemplateRecord | None:
        """Return the template or None."""
        row = self._session.get(Template, template_id)
        return None if row is None else _to_record(row)

    def list(self) -> list[TemplateRecord]:
        """Return all templates, oldest first."""
        rows = self._session.scalars(select(Template).order_by(Template.created_at, Template.id))
        return [_to_record(r) for r in rows]

    def add(self, campaign_id: UUID, template: TemplateRecord) -> None:
        """Persist a new template."""
        values = {f: getattr(template, f) for f in _TEMPLATE_FIELDS}
        self._session.add(Template(id=template.id, campaign_id=campaign_id, **values))
        self._session.flush()

    def save(self, template: TemplateRecord) -> None:
        """Persist changes to an existing template."""
        row = self._session.get(Template, template.id)
        if row is None:
            raise LookupError("template does not exist")
        for field in _TEMPLATE_FIELDS:
            setattr(row, field, getattr(template, field))
        self._session.flush()

    def add_consent(
        self, campaign_id: UUID, template_id: UUID, file_key: str, content_type: str
    ) -> None:
        """Record a confirmed consent file."""
        self._session.add(
            ConsentRecord(
                campaign_id=campaign_id,
                template_id=template_id,
                file_key=file_key,
                content_type=content_type,
                confirmed=True,
            )
        )
        self._session.flush()


class AuditRepository:
    """Append-only audit trail: there is deliberately no update or delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, *, campaign_id: UUID, actor: str, action: str, at: datetime, details: dict[str, Any]
    ) -> None:
        """Append an entry."""
        self._session.add(
            AuditLog(campaign_id=campaign_id, actor=actor, action=action, at=at, details=details)
        )
        self._session.flush()

    def list(self, *, campaign_id: UUID, action: str | None = None) -> list[AuditEntry]:
        """Return entries oldest first, optionally only one action."""
        query = select(AuditLog).where(AuditLog.campaign_id == campaign_id)
        if action is not None:
            query = query.where(AuditLog.action == action)
        rows = self._session.scalars(query.order_by(AuditLog.at, AuditLog.id))
        return [AuditEntry(r.at, r.actor, r.action, dict(r.details)) for r in rows]


@dataclass(frozen=True)
class NewRow:
    """A row to store; name and ID are plaintext here and encrypted by the repository."""

    row_number: int
    name: str
    voter_id: str
    spoken_name: str | None = None
    status: str = "QUEUED"
    failure_code: str | None = None


@dataclass(frozen=True)
class StoredRow:
    """A row read back and decrypted."""

    row_number: int
    name: str
    voter_id: str
    spoken_name: str | None
    status: str
    key_id: str


class BatchRepository:
    """Batches and their rows, with encryption of personal data."""

    def __init__(self, session: Session, cipher: Cipher) -> None:
        self._session = session
        self._cipher = cipher

    def create_batch(self, campaign_id: UUID, template_id: UUID) -> UUID:
        """Create an empty draft batch and return its id."""
        batch = Batch(campaign_id=campaign_id, template_id=template_id, status="DRAFT")
        self._session.add(batch)
        self._session.flush()
        return batch.id

    def add_rows(self, batch_id: UUID, rows: list[NewRow]) -> None:
        """Encrypt and store rows."""
        campaign_id = self._session.execute(
            select(Batch.campaign_id).where(Batch.id == batch_id)
        ).scalar_one()
        for row in rows:
            name_enc = self._cipher.encrypt(row.name)
            self._session.add(
                BatchRow(
                    campaign_id=campaign_id,
                    batch_id=batch_id,
                    row_number=row.row_number,
                    status=row.status,
                    name_enc=name_enc,
                    spoken_name_enc=(
                        None if row.spoken_name is None else self._cipher.encrypt(row.spoken_name)
                    ),
                    voter_id_enc=self._cipher.encrypt(row.voter_id),
                    voter_id_index=self._cipher.blind_index(row.voter_id),
                    key_id=_key_id_of(self._cipher, name_enc),
                    failure_code=row.failure_code,
                )
            )
        self._session.flush()

    def rows(self, batch_id: UUID) -> list[StoredRow]:
        """Return the batch's rows in sheet order, decrypted."""
        query = select(BatchRow).where(BatchRow.batch_id == batch_id).order_by(BatchRow.row_number)
        return [self._decrypt(r) for r in self._session.scalars(query)]

    def find_by_voter_id(self, batch_id: UUID, voter_id: str) -> StoredRow | None:
        """Find a row of this batch by ID using the blind index."""
        query = (
            select(BatchRow)
            .where(
                BatchRow.batch_id == batch_id,
                BatchRow.voter_id_index == self._cipher.blind_index(voter_id),
            )
            .order_by(BatchRow.row_number)
            .limit(1)
        )
        row = self._session.scalars(query).first()
        return None if row is None else self._decrypt(row)

    def delete_batch(self, batch_id: UUID) -> None:
        """Delete a batch; the database cascades to its rows."""
        self._session.execute(delete(Batch).where(Batch.id == batch_id))

    def _decrypt(self, row: BatchRow) -> StoredRow:
        """Decrypt one row."""
        spoken = row.spoken_name_enc
        return StoredRow(
            row_number=row.row_number,
            name=self._cipher.decrypt(bytes(row.name_enc)),
            voter_id=self._cipher.decrypt(bytes(row.voter_id_enc)),
            spoken_name=None if spoken is None else self._cipher.decrypt(bytes(spoken)),
            status=row.status,
            key_id=row.key_id,
        )


def _key_id_of(cipher: Cipher, blob: bytes) -> str:
    """Key id stored in a ciphertext (ADR-005); every cipher implementation exposes it."""
    return str(cipher.key_id_of(blob))  # type: ignore[attr-defined]
