"""Provider cost and measured-run queries (render providers, ADR-013 amendment A1).

A batch without a provider id belongs to the default provider, so ``include_unrouted`` widens
the match to those batches. Money is stored with six decimals and read back as floats.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from vidgen.domain.providers import COMPLETED, MeasuredRun
from vidgen.infrastructure.db.models import Batch, BatchRow


def _owned_by(provider_id: str, include_unrouted: bool) -> ColumnElement[bool]:
    condition = Batch.provider_id == provider_id
    return or_(condition, Batch.provider_id.is_(None)) if include_unrouted else condition


def provider_spent(session: Session, provider_id: str, include_unrouted: bool) -> float:
    """Sum of the measured cost of every row a provider rendered."""
    query = (
        select(func.sum(BatchRow.cost_usd))
        .join(Batch, Batch.id == BatchRow.batch_id)
        .where(_owned_by(provider_id, include_unrouted))
    )
    return float(session.execute(query).scalar_one() or 0)


class BatchProviderMixin:
    """Provider queries of the batch store; mixed into ``SqlBatchStore``."""

    _session: Session

    def batch_spent(self, batch_id: UUID) -> float:
        """Measured cost (USD) of this batch's rows."""
        query = select(func.sum(BatchRow.cost_usd)).where(BatchRow.batch_id == batch_id)
        return float(self._session.execute(query).scalar_one() or 0)

    def provider_spent(self, provider_id: str, include_unrouted: bool) -> float:
        """Measured cost of every row the provider rendered."""
        return provider_spent(self._session, provider_id, include_unrouted)

    def provider_runs(
        self, provider_id: str, include_unrouted: bool, limit: int
    ) -> list[MeasuredRun]:
        """The latest completed rows the provider rendered, with their render time."""
        query = (
            select(BatchRow.render_seconds)
            .join(Batch, Batch.id == BatchRow.batch_id)
            .where(
                _owned_by(provider_id, include_unrouted),
                BatchRow.status == COMPLETED,
                BatchRow.render_seconds.is_not(None),
            )
            .order_by(BatchRow.finished_at.desc().nulls_last(), BatchRow.id)
            .limit(limit)
        )
        return [MeasuredRun(COMPLETED, float(s)) for s in self._session.scalars(query) if s]
