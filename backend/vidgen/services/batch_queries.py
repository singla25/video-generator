"""Read-side use cases: batch details, history, status, rows, report, daily statistics (AC14)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

from vidgen.domain.codes import FailureCode, plain_message
from vidgen.domain.stats import ETA_WINDOW, eta_seconds
from vidgen.domain.status import BatchListView
from vidgen.ports.batches import DayStat, RowView
from vidgen.services.batch_rules import (
    counts_from,
    day_series,
    matches_search,
    page_count,
    progress_percent,
)
from vidgen.services.batch_support import (
    BatchContext,
    describe,
    describe_preview,
    load_batch,
    read_preview_stage,
)
from vidgen.services.batch_views import BatchStatus, BatchView, FailureGroup, RowsPage
from vidgen.services.errors import BatchNotFoundError


def failure_message(code: str) -> str:
    """Plain message for a stored failure code; unknown codes get the generic text."""
    try:
        return plain_message(FailureCode(code))
    except ValueError:
        return plain_message(FailureCode.INTERNAL_ERROR)


class BatchQueries:
    """Reads only; nothing here changes state."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx

    def get(self, batch_id: UUID) -> BatchView:
        """One batch with its counts."""
        with self._ctx.uow() as uow:
            return describe_preview(self._ctx, uow, load_batch(uow, batch_id))

    def history(
        self, page: int, page_size: int, view: BatchListView = BatchListView.ALL
    ) -> tuple[list[BatchView], int]:
        """Newest-first page of the batches in ``view`` (each with counts) and the view's total."""
        with self._ctx.uow() as uow:
            batches, total = uow.batches.list_page((page - 1) * page_size, page_size, view)
            counts = uow.batches.counts([b.id for b in batches])
            views = [
                replace(
                    describe(uow, b, counts=counts_from(counts[b.id])),
                    preview_stage=read_preview_stage(self._ctx, b),
                )
                for b in batches
            ]
        return views, total

    def status(self, batch_id: UUID) -> BatchStatus:
        """Counts, progress, ETA and the failure breakdown from one snapshot (B7, C1)."""
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            counts = counts_from(uow.batches.counts([batch_id])[batch_id])
            recent = uow.batches.recent_render_seconds(batch_id, ETA_WINDOW)
            breakdown = uow.batches.failure_breakdown(batch_id)
        return BatchStatus(
            counts=counts,
            progress_percent=progress_percent(counts),
            eta_seconds=eta_seconds(counts.remaining, recent),
            failures=[FailureGroup(c, n, failure_message(c)) for c, n in breakdown],
        )

    def rows(
        self,
        batch_id: UUID,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
        failure_code: str | None = None,
    ) -> RowsPage:
        """A page of rows; search runs here on decrypted values and never leaves the service."""
        offset = (page - 1) * page_size
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            # Counts come from the same transaction as the rows, so a header built from
            # them can never disagree with the table (W-4b).
            counts = counts_from(uow.batches.counts([batch_id])[batch_id])
            if not search:
                rows, total = uow.batches.rows_page(
                    batch_id, status, offset, page_size, failure_code
                )
            else:
                statuses = [status] if status else None
                found = [
                    r
                    for r in uow.batches.iter_rows(batch_id, statuses, failure_code)
                    if matches_search(search, r.name, r.voter_id)
                ]
                total, rows = len(found), found[offset : offset + page_size]
        pages = page_count(total, page_size)
        return RowsPage(rows, page, page_size, total, pages, counts, progress_percent(counts))

    def row(self, batch_id: UUID, row_number: int) -> RowView:
        """One row, or not-found."""
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            found = uow.batches.get_row(batch_id, row_number)
        if found is None:
            raise BatchNotFoundError
        return found

    def daily(self, days: int) -> list[tuple[date, DayStat]]:
        """Completed videos per UTC day for the last ``days`` days, zero days included."""
        last = self._ctx.clock.now().date()
        first = last - timedelta(days=days - 1)
        with self._ctx.uow() as uow:
            stats = uow.batches.daily_stats(first, last)
        return day_series(last, days, stats)
