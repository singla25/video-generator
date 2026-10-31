"""SQL conditions of the batch list views (DD-37).

The views are decided in the database so that pages and totals count only matching batches.
A batch is "failed" when it has at least one FAILED row, checked with an EXISTS subquery.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, exists

from vidgen.domain.status import BatchListView
from vidgen.infrastructure.db.models import Batch, BatchRow

LIVE_STATUSES = ("RUNNING", "PAUSED")
STARTED_STATUSES = ("RUNNING", "PAUSED", "COMPLETED")


def _has_failed_row() -> ColumnElement[bool]:
    """True when the batch has at least one FAILED row."""
    return exists().where(BatchRow.batch_id == Batch.id, BatchRow.status == "FAILED")


def view_condition(view: BatchListView) -> ColumnElement[bool] | None:
    """The WHERE condition of ``view``; None means no filter (every batch)."""
    if view is BatchListView.RUNNING:
        return Batch.status.in_(LIVE_STATUSES)
    if view is BatchListView.COMPLETED:
        return (Batch.status == "COMPLETED") & ~_has_failed_row()
    if view is BatchListView.FAILED:
        return Batch.status.in_(STARTED_STATUSES) & _has_failed_row()
    return None
