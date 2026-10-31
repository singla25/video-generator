"""Start limit of the batch store: rows beyond the requested number are skipped (DD-37).

The first N QUEUED rows in sheet order are kept; the rest become SKIPPED with NOT_SELECTED in
one UPDATE, so the caller's transaction either sees all of it or none of it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vidgen.domain.codes import FailureCode
from vidgen.infrastructure.db.models import BatchRow


class BatchLimitMixin:
    """Skipping of unselected rows; mixed into ``SqlBatchStore`` (which provides the session)."""

    _session: Session

    def skip_unselected(self, batch_id: UUID, limit: int) -> int:
        """Mark QUEUED rows after the first ``limit`` (sheet order) SKIPPED as NOT_SELECTED."""
        kept = (
            select(BatchRow.id)
            .where(BatchRow.batch_id == batch_id, BatchRow.status == "QUEUED")
            .order_by(BatchRow.row_number)
            .limit(limit)
        )
        result = self._session.execute(
            update(BatchRow)
            .where(
                BatchRow.batch_id == batch_id,
                BatchRow.status == "QUEUED",
                BatchRow.id.not_in(kept),
            )
            .values(status="SKIPPED", failure_code=FailureCode.NOT_SELECTED.value)
        )
        return int(getattr(result, "rowcount", 0))
