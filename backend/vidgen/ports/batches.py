"""Batch data types and the ports used by the batch services (T12).

Pure data and Protocols: no I/O and no framework imports.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from vidgen.domain.status import ApprovalFingerprint

PREVIEW_NONE = "NONE"
PREVIEW_PENDING = "PENDING"
PREVIEW_READY = "READY"
PREVIEW_FAILED = "FAILED"


@dataclass(frozen=True)
class MappingRecord:
    """Which sheet columns hold the name, the ID and the optional spoken name."""

    name_column: str
    id_column: str
    spoken_name_column: str | None
    name_index: int
    id_index: int
    spoken_name_index: int | None

    @property
    def indexes(self) -> tuple[int | None, ...]:
        """Column indexes in a fixed order, used in the approval fingerprint."""
        return (self.name_index, self.id_index, self.spoken_name_index)


@dataclass(frozen=True)
class PreviewRecord:
    """State of the preview render and of its approval (AC7, A5)."""

    status: str = PREVIEW_NONE
    key: str | None = None
    row_id: UUID | None = None
    failure_code: str | None = None
    requested_for: ApprovalFingerprint | None = None
    rendered_for: ApprovalFingerprint | None = None
    approved_for: ApprovalFingerprint | None = None


@dataclass
class BatchRecord:
    """A batch as the services see it."""

    id: UUID
    template_id: UUID
    status: str
    created_at: datetime
    sheet_key: str | None = None
    sheet_name: str | None = None
    folder_name: str | None = None
    idempotency_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    mapping: MappingRecord | None = None
    preview: PreviewRecord = field(default_factory=PreviewRecord)


@dataclass(frozen=True)
class NewBatchRow:
    """A row to store; name and ID are plaintext here and encrypted by the store."""

    row_number: int
    name: str
    voter_id: str
    spoken_name: str | None
    status: str
    failure_code: str | None = None


@dataclass(frozen=True)
class RowView:
    """A stored row with its personal data decrypted (admin responses only, B6)."""

    id: UUID
    row_number: int
    status: str
    name: str
    voter_id: str
    spoken_name: str | None
    failure_code: str | None
    render_seconds: float | None
    output_key: str | None


@dataclass(frozen=True)
class DayStat:
    """Completed videos on one UTC day."""

    videos: int
    avg_render_seconds: float | None


class BatchStore(Protocol):
    """Persistence for batches and rows. Mutating methods run in the caller's transaction."""

    def add(self, campaign_id: UUID, batch: BatchRecord) -> None:
        """Insert a new batch."""
        ...

    def get(self, batch_id: UUID, *, lock: bool = False) -> BatchRecord | None:
        """Return a batch; ``lock`` takes a row lock for the rest of the transaction."""
        ...

    def save(self, batch: BatchRecord) -> None:
        """Write the batch's changes."""
        ...

    def delete(self, batch_id: UUID) -> None:
        """Delete a batch; the database removes its rows."""
        ...

    def list_page(self, offset: int, limit: int) -> tuple[list[BatchRecord], int]:
        """Newest-first page of batches and the total count."""
        ...

    def by_idempotency_key(self, key: str) -> UUID | None:
        """Id of the batch that used this start key, if any."""
        ...

    def folders_in_use(self) -> set[str]:
        """Output folder names already given to batches."""
        ...

    def expired(self, cutoff: datetime) -> list[UUID]:
        """Batches the retention job must delete (A8, B12)."""
        ...

    def replace_rows(self, campaign_id: UUID, batch_id: UUID, rows: Iterable[NewBatchRow]) -> None:
        """Delete the batch's rows and store ``rows`` (streamed, written in chunks)."""
        ...

    def counts(self, batch_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
        """Row counts by status for each batch."""
        ...

    def first_live_row_id(self, batch_id: UUID) -> UUID | None:
        """The first row that is not SKIPPED (the preview row)."""
        ...

    def queued_row_ids(self, batch_id: UUID) -> list[UUID]:
        """Ids of QUEUED rows in sheet order."""
        ...

    def cancel_queued(self, batch_id: UUID, finished_at: datetime) -> int:
        """Turn QUEUED rows into CANCELLED; returns how many."""
        ...

    def requeue_failed(self, batch_id: UUID) -> list[UUID]:
        """Turn FAILED rows into QUEUED (clearing the failure code); returns their ids."""
        ...

    def get_row(self, batch_id: UUID, row_number: int) -> RowView | None:
        """One row by sheet row number."""
        ...

    def rows_page(
        self,
        batch_id: UUID,
        status: str | None,
        offset: int,
        limit: int,
        failure_code: str | None = None,
    ) -> tuple[list[RowView], int]:
        """A page of rows in sheet order plus the number of matching rows."""
        ...

    def iter_rows(
        self, batch_id: UUID, statuses: list[str] | None = None, failure_code: str | None = None
    ) -> Iterator[RowView]:
        """All (optionally filtered) rows in sheet order, fetched in chunks."""
        ...

    def failure_breakdown(self, batch_id: UUID) -> list[tuple[str, int]]:
        """(code, count) of FAILED rows, biggest group first."""
        ...

    def recent_render_seconds(self, batch_id: UUID, limit: int) -> list[float]:
        """Render times of the last completed rows, oldest first."""
        ...

    def daily_stats(self, first_day: date, last_day: date) -> dict[date, DayStat]:
        """Completed rows per UTC day, previews excluded."""
        ...

    def output_keys(self, batch_id: UUID) -> list[str]:
        """Storage keys of every rendered output file."""
        ...


class JobQueue(Protocol):
    """Hands render work to the workers. The API never renders (CLAUDE.md section 4)."""

    def enqueue_preview(self, batch_id: UUID, row_id: UUID) -> None:
        """Queue the preview render of one row."""
        ...

    def enqueue_rows(self, batch_id: UUID, row_ids: list[UUID]) -> None:
        """Queue one render job per row."""
        ...
