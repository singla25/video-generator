"""The batch service: one entry point that delegates to the focused collaborators."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from vidgen.domain.codes import FailureCode
from vidgen.ports.batches import DayStat
from vidgen.services.batch_create import BatchCreator, MappingRequest
from vidgen.services.batch_downloads import BatchDownloads, ZipPlan
from vidgen.services.batch_flow import BatchFlow
from vidgen.services.batch_queries import BatchQueries
from vidgen.services.batch_retention import BatchRetention
from vidgen.services.batch_support import BatchContext
from vidgen.services.batch_views import BatchReport, BatchStatus, BatchView, RowsPage
from vidgen.services.sheet_inspect import SheetInspection, inspect_sheet


class BatchService:
    """Everything the API and the workers can do with batches."""

    def __init__(self, ctx: BatchContext) -> None:
        self._reader = ctx.reader
        self._create = BatchCreator(ctx)
        self._flow = BatchFlow(ctx)
        self._queries = BatchQueries(ctx)
        self._downloads = BatchDownloads(ctx, self._queries)
        self._retention = BatchRetention(ctx)

    # creation and drafts
    def create(self, sheet: Path, template_id: UUID, request: MappingRequest) -> BatchView:
        """Validate a sheet and create a draft batch."""
        return self._create.create(sheet, template_id, request)

    def change_mapping(self, batch_id: UUID, request: MappingRequest) -> BatchView:
        """Re-read the stored sheet with other columns."""
        return self._create.change_mapping(batch_id, request)

    def change_template(self, batch_id: UUID, template_id: UUID) -> BatchView:
        """Use another usable template for a draft."""
        return self._create.change_template(batch_id, template_id)

    def report(self, batch_id: UUID) -> BatchReport:
        """The validation report."""
        return self._create.report(batch_id)

    # preview, start, control
    def request_preview(self, batch_id: UUID) -> BatchView:
        """Queue the preview render."""
        return self._flow.request_preview(batch_id)

    def approve_preview(self, batch_id: UUID) -> BatchView:
        """Approve the rendered preview."""
        return self._flow.approve_preview(batch_id)

    def preview_rendered(self, batch_id: UUID, key: str) -> None:
        """Worker hook: preview stored at ``key``."""
        self._flow.preview_rendered(batch_id, key)

    def preview_failed(self, batch_id: UUID, code: FailureCode) -> None:
        """Worker hook: preview failed with ``code``."""
        self._flow.preview_failed(batch_id, code)

    def preview_key(self, batch_id: UUID) -> str:
        """Storage key of the rendered preview."""
        return self._flow.preview_key(batch_id)

    def start(self, batch_id: UUID, idempotency_key: str, folder_name: str | None) -> BatchView:
        """Start the batch."""
        return self._flow.start(batch_id, idempotency_key, folder_name)

    def pause(self, batch_id: UUID) -> BatchView:
        """Pause the batch."""
        return self._flow.pause(batch_id)

    def resume(self, batch_id: UUID) -> BatchView:
        """Resume the batch."""
        return self._flow.resume(batch_id)

    def cancel(self, batch_id: UUID) -> BatchView:
        """Cancel the batch."""
        return self._flow.cancel(batch_id)

    def retry_failed(self, batch_id: UUID) -> BatchView:
        """Queue failed rows again."""
        return self._flow.retry_failed(batch_id)

    # reads
    def get(self, batch_id: UUID) -> BatchView:
        """One batch."""
        return self._queries.get(batch_id)

    def history(self, page: int, page_size: int) -> tuple[list[BatchView], int]:
        """Batch history page."""
        return self._queries.history(page, page_size)

    def status(self, batch_id: UUID) -> BatchStatus:
        """Live status of a batch."""
        return self._queries.status(batch_id)

    def rows(
        self,
        batch_id: UUID,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
        failure_code: str | None = None,
    ) -> RowsPage:
        """A page of rows."""
        return self._queries.rows(batch_id, status, search, page, page_size, failure_code)

    def inspect_sheet(self, sheet: Path) -> SheetInspection:
        """Headers, a sample and the row count of an uploaded sheet; nothing is stored."""
        return inspect_sheet(self._reader, sheet)

    def daily(self, days: int) -> list[tuple[date, DayStat]]:
        """Videos per day."""
        return self._queries.daily(days)

    # downloads
    def video(self, batch_id: UUID, row_number: int) -> tuple[str, BinaryIO]:
        """One rendered video."""
        return self._downloads.video(batch_id, row_number)

    def zip_plan(self, batch_id: UUID) -> ZipPlan:
        """Archive contents."""
        return self._downloads.zip_plan(batch_id)

    def failures_csv(self, batch_id: UUID) -> str:
        """Failures CSV text."""
        return self._downloads.failures_csv(batch_id)

    # removal
    def delete(self, batch_id: UUID) -> None:
        """Delete a batch and everything it owns."""
        self._retention.delete(batch_id)

    def run_retention(self) -> int:
        """Delete expired batches; returns how many."""
        return self._retention.run_retention()
