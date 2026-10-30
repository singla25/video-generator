"""Recover rows whose queue message was lost (Redis flush or restart). No migration needed.

Idempotent: a row that still has a live job is skipped, so running this twice never duplicates
work. Logs hold counts only, never names or voter IDs.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from vidgen.ports.batches import BatchStore, JobQueue, StuckRow
from vidgen.ports.interfaces import Clock

logger = logging.getLogger(__name__)

DEFAULT_STUCK_AFTER_SECONDS = 600
DEFAULT_PAGE_SIZE = 500


class _Uow(Protocol):
    @property
    def batches(self) -> BatchStore: ...


@dataclass
class _Tally:
    requeued: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class RequeueReport:
    """What one recovery pass did."""

    requeued: int
    skipped_live: int
    queue_down: bool


def requeue_stuck_rows(
    open_uow: Callable[[], AbstractContextManager[_Uow]],
    queue: JobQueue,
    clock: Clock,
    *,
    stuck_after_seconds: int = DEFAULT_STUCK_AFTER_SECONDS,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RequeueReport:
    """Re-enqueue QUEUED rows and pending previews that have no live job.

    Reads candidates page by page. A queue outage is logged and ends the pass without raising.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    cutoff = clock.now() - timedelta(seconds=stuck_after_seconds)
    tally = _Tally()
    after: UUID | None = None
    try:
        while True:
            with open_uow() as uow:
                page = uow.batches.stuck_candidates(cutoff, after, page_size)
            if not page:
                break
            after = page[-1].row_id
            _requeue_page(queue, page, tally)
    except Exception as exc:
        if not _is_queue_error(exc):
            raise
        logger.warning(
            "requeue stopped: queue unavailable",
            extra={"error_type": type(exc).__name__, "requeued": tally.requeued},
        )
        return RequeueReport(tally.requeued, tally.skipped, queue_down=True)
    logger.info(
        "requeue finished", extra={"requeued": tally.requeued, "skipped_live": tally.skipped}
    )
    return RequeueReport(tally.requeued, tally.skipped, queue_down=False)


def _is_queue_error(exc: Exception) -> bool:
    """Broker errors (redis, dramatiq) are recognised by module, keeping services import-clean."""
    return isinstance(exc, OSError) or type(exc).__module__.startswith(("redis", "dramatiq"))


def _requeue_page(queue: JobQueue, page: list[StuckRow], tally: _Tally) -> None:
    """Enqueue the page's rows without a live job, counting as it goes (kept on error)."""
    by_batch: dict[UUID, list[UUID]] = defaultdict(list)
    for item in page:
        if queue.has_live_job(item.row_id):
            tally.skipped += 1
        elif item.kind == "preview":
            queue.enqueue_preview(item.batch_id, item.row_id)
            tally.requeued += 1
        else:
            by_batch[item.batch_id].append(item.row_id)
    for batch_id, row_ids in by_batch.items():
        queue.enqueue_rows(batch_id, row_ids)
        tally.requeued += len(row_ids)
