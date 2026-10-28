"""SQLAlchemy implementation of ``BatchStore`` (T12).

Personal data is encrypted on the way in and decrypted only when a row is read for the admin.
Bulk writes use Core statements, so 100,000 rows never sit in the ORM identity map.
Extra batch state (column mapping, sheet name, preview) is kept as one JSON document in
``batches.column_mapping``: column names and ids, plus the confirmed spoken name as ciphertext.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime
from itertools import islice
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.db.batch_documents import apply_to_row, to_record
from vidgen.infrastructure.db.batch_stats_store import BatchStatsMixin
from vidgen.infrastructure.db.models import Batch, BatchRow
from vidgen.ports.batches import (
    BatchRecord,
    NewBatchRow,
    RowView,
)

if TYPE_CHECKING:
    from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher

INSERT_CHUNK = 1000
FETCH_CHUNK = 1000
FINISHED_STATUSES = ("COMPLETED", "CANCELLED")
FALLBACK_FAILURE_CODE = FailureCode.INTERNAL_ERROR.value


class SqlBatchStore(BatchStatsMixin):
    """Batches and rows in Postgres."""

    def __init__(self, session: Session, cipher: AesGcmCipher) -> None:
        self._session = session
        self._cipher = cipher

    # batches

    def add(self, campaign_id: UUID, batch: BatchRecord) -> None:
        """Insert a new batch."""
        row = Batch(id=batch.id, campaign_id=campaign_id)
        apply_to_row(row, batch, self._cipher)
        self._session.add(row)
        self._session.flush()

    def get(self, batch_id: UUID, *, lock: bool = False) -> BatchRecord | None:
        """Return a batch, optionally locking its row."""
        query = select(Batch).where(Batch.id == batch_id)
        if lock:
            query = query.with_for_update()
        row = self._session.execute(query).scalar_one_or_none()
        return None if row is None else to_record(row, self._cipher)

    def save(self, batch: BatchRecord) -> None:
        """Write the batch's changes."""
        row = self._session.get(Batch, batch.id)
        if row is None:
            raise LookupError("batch does not exist")
        apply_to_row(row, batch, self._cipher)
        self._session.flush()

    def delete(self, batch_id: UUID) -> None:
        """Delete a batch; the database cascades to its rows."""
        self._session.execute(delete(Batch).where(Batch.id == batch_id))

    def list_page(self, offset: int, limit: int) -> tuple[list[BatchRecord], int]:
        """Newest-first page of batches and the total."""
        query = select(Batch).order_by(Batch.created_at.desc(), Batch.id.desc())
        rows = self._session.scalars(query.offset(offset).limit(limit))
        total = self._session.execute(select(func.count()).select_from(Batch)).scalar_one()
        return [to_record(r, self._cipher) for r in rows], int(total)

    def by_idempotency_key(self, key: str) -> UUID | None:
        """Id of the batch that used this start key."""
        query = select(Batch.id).where(Batch.idempotency_key == key)
        return self._session.execute(query).scalar_one_or_none()

    def folders_in_use(self) -> set[str]:
        """Output folder names already given to batches."""
        names = self._session.scalars(
            select(Batch.folder_name).where(Batch.folder_name.is_not(None))
        )
        return {name for name in names if name}

    def expired(self, cutoff: datetime) -> list[UUID]:
        """Finished batches past ``cutoff`` and drafts created before it (A8, B12)."""
        finished = Batch.status.in_(FINISHED_STATUSES) & (Batch.finished_at < cutoff)
        draft = (Batch.status == "DRAFT") & (Batch.created_at < cutoff)
        return list(self._session.scalars(select(Batch.id).where(finished | draft)))

    # rows: writing

    def replace_rows(self, campaign_id: UUID, batch_id: UUID, rows: Iterable[NewBatchRow]) -> None:
        """Delete the batch's rows and store ``rows`` in chunks."""
        self._session.execute(delete(BatchRow).where(BatchRow.batch_id == batch_id))
        iterator = iter(rows)
        while chunk := list(islice(iterator, INSERT_CHUNK)):
            values = [self._row_values(campaign_id, batch_id, row) for row in chunk]
            try:
                self._session.execute(insert(BatchRow), values)
            except IntegrityError as exc:
                raise DomainError(FailureCode.DUPLICATE_ID) from exc

    def _row_values(self, campaign_id: UUID, batch_id: UUID, row: NewBatchRow) -> dict[str, Any]:
        name_enc = self._cipher.encrypt(row.name)
        spoken = row.spoken_name
        return {
            "campaign_id": campaign_id,
            "batch_id": batch_id,
            "row_number": row.row_number,
            "status": row.status,
            "name_enc": name_enc,
            "spoken_name_enc": None if spoken is None else self._cipher.encrypt(spoken),
            "voter_id_enc": self._cipher.encrypt(row.voter_id),
            "voter_id_index": self._cipher.blind_index(row.voter_id),
            "key_id": self._cipher.key_id_of(name_enc),
            "failure_code": row.failure_code,
            "attempts": 0,
        }

    def cancel_queued(self, batch_id: UUID, finished_at: datetime) -> int:
        """Turn QUEUED rows into CANCELLED."""
        result = self._session.execute(
            update(BatchRow)
            .where(BatchRow.batch_id == batch_id, BatchRow.status == "QUEUED")
            .values(status="CANCELLED", finished_at=finished_at)
        )
        return int(getattr(result, "rowcount", 0))

    def requeue_failed(self, batch_id: UUID) -> list[UUID]:
        """Turn FAILED rows into QUEUED in one statement, so two retries never share a row."""
        result = self._session.execute(
            update(BatchRow)
            .where(BatchRow.batch_id == batch_id, BatchRow.status == "FAILED")
            .values(
                status="QUEUED", failure_code=None, attempts=0, started_at=None, finished_at=None
            )
            .returning(BatchRow.id, BatchRow.row_number)
        )
        return [row_id for row_id, _ in sorted(result.all(), key=lambda r: r[1])]

    def requeue_row(self, batch_id: UUID, row_number: int) -> UUID | None:
        """Turn one FAILED row into QUEUED in one statement; the attempt history is kept."""
        result = self._session.execute(
            update(BatchRow)
            .where(
                BatchRow.batch_id == batch_id,
                BatchRow.row_number == row_number,
                BatchRow.status == "FAILED",
            )
            .values(status="QUEUED", failure_code=None, started_at=None, finished_at=None)
            .returning(BatchRow.id)
        )
        return result.scalar_one_or_none()

    # rows: reading

    def counts(self, batch_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
        """Row counts by status for each batch."""
        found: dict[UUID, dict[str, int]] = {batch_id: {} for batch_id in batch_ids}
        query = (
            select(BatchRow.batch_id, BatchRow.status, func.count())
            .where(BatchRow.batch_id.in_(batch_ids))
            .group_by(BatchRow.batch_id, BatchRow.status)
        )
        for batch_id, status, count in self._session.execute(query):
            found[batch_id][status] = int(count)
        return found

    def first_live_row_id(self, batch_id: UUID) -> UUID | None:
        """The first non-SKIPPED row."""
        query = (
            select(BatchRow.id)
            .where(BatchRow.batch_id == batch_id, BatchRow.status != "SKIPPED")
            .order_by(BatchRow.row_number)
            .limit(1)
        )
        return self._session.execute(query).scalar_one_or_none()

    def queued_row_ids(self, batch_id: UUID) -> list[UUID]:
        """Ids of QUEUED rows in sheet order."""
        query = (
            select(BatchRow.id)
            .where(BatchRow.batch_id == batch_id, BatchRow.status == "QUEUED")
            .order_by(BatchRow.row_number)
        )
        return list(self._session.scalars(query))

    def get_row(self, batch_id: UUID, row_number: int) -> RowView | None:
        """One row by sheet row number."""
        query = select(BatchRow).where(
            BatchRow.batch_id == batch_id, BatchRow.row_number == row_number
        )
        row = self._session.execute(query).scalar_one_or_none()
        return None if row is None else self._view(row)

    def get_row_by_id(self, batch_id: UUID, row_id: UUID) -> RowView | None:
        """One row by its id."""
        query = select(BatchRow).where(BatchRow.batch_id == batch_id, BatchRow.id == row_id)
        row = self._session.execute(query).scalar_one_or_none()
        return None if row is None else self._view(row)

    def rows_page(
        self,
        batch_id: UUID,
        status: str | None,
        offset: int,
        limit: int,
        failure_code: str | None = None,
    ) -> tuple[list[RowView], int]:
        """A page of rows in sheet order plus the number of matching rows."""
        condition = [BatchRow.batch_id == batch_id]
        if status is not None:
            condition.append(BatchRow.status == status)
        if failure_code is not None:
            condition.append(BatchRow.failure_code == failure_code)
        total = self._session.execute(
            select(func.count()).select_from(BatchRow).where(*condition)
        ).scalar_one()
        query = select(BatchRow).where(*condition).order_by(BatchRow.row_number)
        rows = self._session.scalars(query.offset(offset).limit(limit))
        return [self._view(r) for r in rows], int(total)

    def iter_rows(
        self, batch_id: UUID, statuses: list[str] | None = None, failure_code: str | None = None
    ) -> Iterator[RowView]:
        """All matching rows in sheet order, fetched in key-ordered chunks."""
        last = -1
        while True:
            query = select(BatchRow).where(
                BatchRow.batch_id == batch_id, BatchRow.row_number > last
            )
            if statuses is not None:
                query = query.where(BatchRow.status.in_(statuses))
            if failure_code is not None:
                query = query.where(BatchRow.failure_code == failure_code)
            chunk = list(
                self._session.scalars(query.order_by(BatchRow.row_number).limit(FETCH_CHUNK))
            )
            if not chunk:
                return
            last = chunk[-1].row_number
            yield from (self._view(r) for r in chunk)

    def _view(self, row: BatchRow) -> RowView:
        spoken = row.spoken_name_enc
        return RowView(
            id=row.id,
            row_number=row.row_number,
            status=row.status,
            name=self._cipher.decrypt(bytes(row.name_enc)),
            voter_id=self._cipher.decrypt(bytes(row.voter_id_enc)),
            spoken_name=None if spoken is None else self._cipher.decrypt(bytes(spoken)),
            failure_code=row.failure_code,
            render_seconds=row.render_seconds,
            output_key=row.output_key,
        )

    # statistics
