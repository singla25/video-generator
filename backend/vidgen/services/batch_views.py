"""Result shapes returned by the batch services (the API turns them into JSON)."""

from __future__ import annotations

from dataclasses import dataclass, field

from vidgen.domain.stats import StatusCounts
from vidgen.ports.batches import BatchRecord, RowView


@dataclass(frozen=True)
class Problem:
    """One skipped row in the validation report."""

    row_number: int
    code: str
    message: str
    faults: list[str]


@dataclass(frozen=True)
class BatchReport:
    """Validation report of a sheet (AC3)."""

    total_rows: int
    valid_rows: int
    skipped_rows: int
    problems: list[Problem] = field(default_factory=list)


@dataclass(frozen=True)
class BatchView:
    """A batch with its counts and optional extras."""

    record: BatchRecord
    counts: StatusCounts
    success_rate: float | None
    preview_status: str
    preview_approved: bool
    report: BatchReport | None = None
    queued_rows: int | None = None
    retried_rows: int | None = None


@dataclass(frozen=True)
class FailureGroup:
    """Failed rows with one code."""

    code: str
    count: int
    message: str


@dataclass(frozen=True)
class BatchStatus:
    """Live status: counts, progress, ETA and failure breakdown (AC14)."""

    counts: StatusCounts
    progress_percent: float
    eta_seconds: float | None
    failures: list[FailureGroup]


@dataclass(frozen=True)
class RowsPage:
    """A page of rows."""

    rows: list[RowView]
    page: int
    page_size: int
    total: int
    total_pages: int
