"""Row and batch state machines and the preview-approval gate (AC7, AC12, AC13, A5, A6)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class IllegalTransitionError(Exception):
    """A status change that the state machine does not allow (a programming error)."""


class PreviewNotReadyError(Exception):
    """A preview was approved before a matching preview was rendered."""


class RowStatus(StrEnum):
    """Lifecycle of one sheet row."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class BatchState(StrEnum):
    """Lifecycle of a batch."""

    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class BatchAction(StrEnum):
    """Operations that move a batch between states."""

    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    FINISH = "FINISH"
    CANCEL = "CANCEL"
    RETRY = "RETRY"


_R = RowStatus
_ROW_TRANSITIONS: frozenset[tuple[RowStatus, RowStatus]] = frozenset(
    {
        (_R.QUEUED, _R.PROCESSING),
        (_R.QUEUED, _R.CANCELLED),
        (_R.PROCESSING, _R.COMPLETED),
        (_R.PROCESSING, _R.FAILED),
        (_R.PROCESSING, _R.QUEUED),  # automatic retry puts the row back in the queue
        (_R.FAILED, _R.QUEUED),  # manual retry-failed
    }
)

_B = BatchState
_A = BatchAction
# Repeated START / PAUSE / CANCEL are deliberate no-ops so retried requests are idempotent (B11).
_BATCH_TRANSITIONS: dict[tuple[BatchState, BatchAction], BatchState] = {
    (_B.DRAFT, _A.START): _B.RUNNING,
    (_B.RUNNING, _A.START): _B.RUNNING,
    (_B.PAUSED, _A.START): _B.PAUSED,
    (_B.RUNNING, _A.PAUSE): _B.PAUSED,
    (_B.PAUSED, _A.PAUSE): _B.PAUSED,
    (_B.PAUSED, _A.RESUME): _B.RUNNING,
    (_B.RUNNING, _A.FINISH): _B.COMPLETED,
    (_B.RUNNING, _A.CANCEL): _B.CANCELLED,
    (_B.PAUSED, _A.CANCEL): _B.CANCELLED,
    (_B.CANCELLED, _A.CANCEL): _B.CANCELLED,
    (_B.DRAFT, _A.CANCEL): _B.CANCELLED,  # D-19: a draft can be discarded
    # Retry-failed (AC13): a finished batch with failed rows runs again.
    (_B.RUNNING, _A.RETRY): _B.RUNNING,
    (_B.PAUSED, _A.RETRY): _B.PAUSED,
    (_B.COMPLETED, _A.RETRY): _B.RUNNING,
}


def can_transition(old: RowStatus, new: RowStatus) -> bool:
    """True if a row may move from ``old`` to ``new``."""
    return (old, new) in _ROW_TRANSITIONS


def transition(old: RowStatus, new: RowStatus) -> RowStatus:
    """Return ``new`` if the move is legal, else raise IllegalTransitionError."""
    if not can_transition(old, new):
        raise IllegalTransitionError(f"{old} -> {new} is not allowed")
    return new


def status_after_cancel(status: RowStatus) -> RowStatus:
    """Cancel only affects queued rows; rows in progress finish (A6)."""
    return RowStatus.CANCELLED if status is RowStatus.QUEUED else status


def status_after_retry_failed(status: RowStatus) -> RowStatus:
    """Retry-failed re-queues only failed rows."""
    return RowStatus.QUEUED if status is RowStatus.FAILED else status


def apply_batch_action(state: BatchState, action: BatchAction) -> BatchState:
    """Return the batch state after ``action`` or raise IllegalTransitionError."""
    try:
        return _BATCH_TRANSITIONS[(state, action)]
    except KeyError:
        raise IllegalTransitionError(f"{action} is not allowed while {state}") from None


@dataclass(frozen=True)
class ApprovalFingerprint:
    """Everything a preview approval depends on; a change invalidates it (A5)."""

    slot_start_s: float
    slot_end_s: float
    template_id: str
    mapping: tuple[int | None, ...]


@dataclass(frozen=True)
class PreviewGate:
    """Which fingerprint was last rendered and which one was approved."""

    rendered_for: ApprovalFingerprint | None = None
    approved_for: ApprovalFingerprint | None = None


def preview_rendered(gate: PreviewGate, fingerprint: ApprovalFingerprint) -> PreviewGate:
    """Record a new preview; any earlier approval no longer applies."""
    return replace(gate, rendered_for=fingerprint, approved_for=None)


def approve_preview(gate: PreviewGate, fingerprint: ApprovalFingerprint) -> PreviewGate:
    """Approve the rendered preview; it must match ``fingerprint``."""
    if gate.rendered_for != fingerprint:
        raise PreviewNotReadyError("render a preview for the current settings first")
    return replace(gate, approved_for=fingerprint)


def can_start(gate: PreviewGate, current: ApprovalFingerprint) -> bool:
    """A batch may start only when the current settings were approved."""
    return gate.approved_for == current
