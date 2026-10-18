"""Row and batch status rules (AC12-E11, AC13, A6). Pure state machine."""

from __future__ import annotations

import itertools

import pytest

from vidgen.domain.status import (
    BatchAction,
    BatchState,
    IllegalTransitionError,
    RowStatus,
    apply_batch_action,
    can_transition,
    status_after_cancel,
    status_after_retry_failed,
    transition,
)

R = RowStatus

LEGAL = {
    (R.QUEUED, R.PROCESSING),
    (R.QUEUED, R.CANCELLED),
    (R.PROCESSING, R.COMPLETED),
    (R.PROCESSING, R.FAILED),
    (R.PROCESSING, R.QUEUED),  # automatic retry is re-queued
    (R.FAILED, R.QUEUED),  # manual retry-failed
}


def test_row_status_members() -> None:
    """R7.1 + A6: six row statuses."""
    assert {s.value for s in R} == {
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "SKIPPED",
        "CANCELLED",
    }


@pytest.mark.parametrize(("old", "new"), sorted(LEGAL))
def test_legal_row_transitions_are_allowed(old: RowStatus, new: RowStatus) -> None:
    """TT-AC12-E11."""
    assert can_transition(old, new)
    assert transition(old, new) is new


@pytest.mark.parametrize(
    ("old", "new"),
    [pair for pair in itertools.product(R, R) if pair not in LEGAL],
)
def test_every_other_row_transition_is_rejected(old: RowStatus, new: RowStatus) -> None:
    """TT-AC12-E11: includes PROCESSING -> CANCELLED (A6) and any exit from terminal states."""
    assert not can_transition(old, new)
    with pytest.raises(IllegalTransitionError):
        transition(old, new)


@pytest.mark.parametrize("terminal", [R.COMPLETED, R.SKIPPED, R.CANCELLED])
def test_terminal_row_states_are_immutable(terminal: RowStatus) -> None:
    """TT-AC12-E11."""
    assert not any(can_transition(terminal, other) for other in R)


def test_cancel_only_changes_queued_rows() -> None:
    """TT-AC13-P3, P6, E1 (A6): PROCESSING rows finish, never become CANCELLED."""
    assert status_after_cancel(R.QUEUED) is R.CANCELLED
    for status in (R.PROCESSING, R.COMPLETED, R.FAILED, R.SKIPPED, R.CANCELLED):
        assert status_after_cancel(status) is status


def test_retry_failed_only_changes_failed_rows() -> None:
    """TT-AC13-P4."""
    assert status_after_retry_failed(R.FAILED) is R.QUEUED
    for status in (R.QUEUED, R.PROCESSING, R.COMPLETED, R.SKIPPED, R.CANCELLED):
        assert status_after_retry_failed(status) is status


# ---- batch-level state ----------------------------------------------------------------

B = BatchState
A = BatchAction


def test_batch_lifecycle_start_pause_resume_finish() -> None:
    """TT-AC13-P1, P2."""
    state = apply_batch_action(B.DRAFT, A.START)
    assert state is B.RUNNING
    state = apply_batch_action(state, A.PAUSE)
    assert state is B.PAUSED
    state = apply_batch_action(state, A.RESUME)
    assert state is B.RUNNING
    assert apply_batch_action(state, A.FINISH) is B.COMPLETED


def test_cancel_is_allowed_while_running_or_paused() -> None:
    """TT-AC13-E2: pause then cancel."""
    assert apply_batch_action(B.RUNNING, A.CANCEL) is B.CANCELLED
    assert apply_batch_action(B.PAUSED, A.CANCEL) is B.CANCELLED


@pytest.mark.parametrize("state", [B.COMPLETED, B.CANCELLED])
def test_pause_on_finished_or_cancelled_batch_is_rejected(state: BatchState) -> None:
    """TT-AC13-N1."""
    with pytest.raises(IllegalTransitionError):
        apply_batch_action(state, A.PAUSE)


@pytest.mark.parametrize("state", [B.DRAFT, B.RUNNING, B.COMPLETED, B.CANCELLED])
def test_resume_on_non_paused_batch_is_rejected(state: BatchState) -> None:
    """TT-AC13-N2, E2 (cancel then resume)."""
    with pytest.raises(IllegalTransitionError):
        apply_batch_action(state, A.RESUME)


def test_repeating_start_pause_or_cancel_is_idempotent() -> None:
    """TT-AC13-E3, E10 (B11): same action twice returns the same state."""
    assert apply_batch_action(B.RUNNING, A.START) is B.RUNNING
    assert apply_batch_action(B.PAUSED, A.START) is B.PAUSED
    assert apply_batch_action(B.PAUSED, A.PAUSE) is B.PAUSED
    assert apply_batch_action(B.CANCELLED, A.CANCEL) is B.CANCELLED


def test_cancelled_or_completed_batch_cannot_be_started() -> None:
    """TT-AC13-N1."""
    for state in (B.COMPLETED, B.CANCELLED):
        with pytest.raises(IllegalTransitionError):
            apply_batch_action(state, A.START)
