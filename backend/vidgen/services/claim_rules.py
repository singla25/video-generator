"""Pure rules for claiming a row and for completing a batch (AC12, AC13, A6).

Kept free of I/O so every case can be tested with plain values. The store applies the result
while it holds the row lock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vidgen.domain.outcomes import RowOutcomeKind
from vidgen.ports.rows import ClaimAction, ClaimDecision, ClaimSnapshot, Completion

QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
RUNNING = "RUNNING"
CANCELLED = "CANCELLED"
COMPLETED = "COMPLETED"
FINISHED_ROW_STATUSES = frozenset({"COMPLETED", "FAILED", "SKIPPED", "CANCELLED"})
_LONG_AGO = datetime.min.replace(tzinfo=UTC)

_CLAIM = ClaimDecision(ClaimAction.CLAIM, RowOutcomeKind.COMPLETED)  # outcome unused when claimed
_NOOP = ClaimDecision(ClaimAction.LEAVE, RowOutcomeKind.NOOP)
_BUSY = ClaimDecision(ClaimAction.LEAVE, RowOutcomeKind.BUSY)
_DEFERRED = ClaimDecision(ClaimAction.LEAVE, RowOutcomeKind.DEFERRED)
_DROP_QUEUED = ClaimDecision(ClaimAction.CANCEL_ROW, RowOutcomeKind.NOOP)


def decide_claim(snapshot: ClaimSnapshot, now: datetime, stale_after: timedelta) -> ClaimDecision:
    """Decide what a worker may do with a row it was told to render.

    A row another worker is processing is left alone until it is stale (its worker died),
    then it is taken over. Queued rows start only while the batch is running; on a cancelled
    batch they are cancelled; otherwise (paused, draft) the job waits.
    """
    if snapshot.row_status in FINISHED_ROW_STATUSES:
        return _NOOP
    if snapshot.row_status == PROCESSING:
        age = now - (snapshot.started_at or _LONG_AGO)
        return _CLAIM if age > stale_after else _BUSY
    if snapshot.batch_status == RUNNING:
        return _CLAIM
    return _DROP_QUEUED if snapshot.batch_status == CANCELLED else _DEFERRED


def decide_completion(batch_status: str, pending_rows: int) -> Completion:
    """What to do with a batch after a row finished.

    Nothing while rows are pending. A running batch completes; a cancelled batch keeps its
    status and cancel time but still gets its manifest (A6, A7); a paused one waits.
    """
    if pending_rows > 0 or batch_status not in (RUNNING, CANCELLED):
        return Completion(None, False)
    return Completion(COMPLETED if batch_status == RUNNING else None, True)
