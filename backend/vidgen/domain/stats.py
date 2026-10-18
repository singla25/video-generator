"""Status counts, ETA and success rate (AC14, B7, C1)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from vidgen.domain.status import RowStatus

ETA_WINDOW = 20  # mean of the most recent completed rows (B7)


@dataclass(frozen=True)
class StatusCounts:
    """Rows per status; the parts must always add up to ``total``."""

    total: int
    completed: int
    processing: int
    queued: int
    failed: int
    skipped: int
    cancelled: int

    @classmethod
    def from_statuses(cls, statuses: Iterable[RowStatus]) -> StatusCounts:
        """Count the given statuses."""
        counter = Counter(statuses)
        return cls(
            total=counter.total(),
            completed=counter[RowStatus.COMPLETED],
            processing=counter[RowStatus.PROCESSING],
            queued=counter[RowStatus.QUEUED],
            failed=counter[RowStatus.FAILED],
            skipped=counter[RowStatus.SKIPPED],
            cancelled=counter[RowStatus.CANCELLED],
        )

    @property
    def remaining(self) -> int:
        """Rows still to render: queued plus processing (C1)."""
        return self.queued + self.processing

    @property
    def is_consistent(self) -> bool:
        """True if the per-status counts add up to the total."""
        parts = (self.completed, self.processing, self.queued)
        parts_rest = (self.failed, self.skipped, self.cancelled)
        return sum(parts) + sum(parts_rest) == self.total


def eta_seconds(remaining: int, recent_render_seconds: Sequence[float]) -> float | None:
    """Remaining rows times the mean of the last 20 render times; None before the first (B7)."""
    if not recent_render_seconds:
        return None
    window = recent_render_seconds[-ETA_WINDOW:]
    return remaining * sum(window) / len(window)


def success_rate(completed: int, failed: int) -> float | None:
    """Completed over completed plus failed; skipped and cancelled are excluded (B7)."""
    finished = completed + failed
    return completed / finished if finished else None
