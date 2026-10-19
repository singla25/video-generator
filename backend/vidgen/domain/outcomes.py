"""What happened to a row job, as reported by the render pipeline."""

from __future__ import annotations

from enum import Enum


class RowOutcomeKind(Enum):
    """Result of one delivery of a row job (a queue message)."""

    COMPLETED = "completed"  # the row now has its output
    FAILED = "failed"  # final failure, recorded on the row
    RETRY = "retry"  # transient failure: the row is queued again, deliver later
    NOOP = "noop"  # nothing to do (finished, cancelled, deleted, or already done)
    BUSY = "busy"  # another worker is rendering this row right now
    DEFERRED = "deferred"  # the batch is not running (paused or draft): try again later
