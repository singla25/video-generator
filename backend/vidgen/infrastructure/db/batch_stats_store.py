"""Statistics queries of the batch store: failure breakdown, render times, daily counts."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vidgen.domain.codes import FailureCode
from vidgen.infrastructure.db.models import BatchRow
from vidgen.ports.batches import DayStat

FALLBACK_FAILURE_CODE = FailureCode.INTERNAL_ERROR.value


class BatchStatsMixin:
    """Read-only statistics; mixed into ``SqlBatchStore`` (which provides the session)."""

    _session: Session

    def failure_breakdown(self, batch_id: UUID) -> list[tuple[str, int]]:
        """(code, count) of FAILED rows, biggest group first."""
        code = func.coalesce(BatchRow.failure_code, FALLBACK_FAILURE_CODE)
        query = (
            select(code, func.count())
            .where(BatchRow.batch_id == batch_id, BatchRow.status == "FAILED")
            .group_by(code)
            .order_by(func.count().desc(), code)
        )
        return [(str(c), int(n)) for c, n in self._session.execute(query)]

    def recent_render_seconds(self, batch_id: UUID, limit: int) -> list[float]:
        """Render times of the last completed rows, oldest first."""
        query = (
            select(BatchRow.render_seconds)
            .where(
                BatchRow.batch_id == batch_id,
                BatchRow.status == "COMPLETED",
                BatchRow.render_seconds.is_not(None),
            )
            .order_by(BatchRow.finished_at.desc(), BatchRow.row_number.desc())
            .limit(limit)
        )
        values = [s for s in self._session.scalars(query) if s is not None]
        return [float(s) for s in reversed(values)]

    def daily_stats(self, first_day: date, last_day: date) -> dict[date, DayStat]:
        """Completed rows per UTC day."""
        start = datetime.combine(first_day, time.min, tzinfo=UTC)
        end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=UTC)
        day = func.date(func.timezone("UTC", BatchRow.finished_at))
        query = (
            select(day, func.count(), func.avg(BatchRow.render_seconds))
            .where(
                BatchRow.status == "COMPLETED",
                BatchRow.finished_at >= start,
                BatchRow.finished_at < end,
            )
            .group_by(day)
        )
        return {
            d: DayStat(int(n), None if avg is None else float(avg))
            for d, n, avg in self._session.execute(query)
        }

    def output_keys(self, batch_id: UUID) -> list[str]:
        """Storage keys of every rendered output."""
        query = select(BatchRow.output_key).where(
            BatchRow.batch_id == batch_id, BatchRow.output_key.is_not(None)
        )
        return [key for key in self._session.scalars(query) if key]
