"""Status counts, ETA and success rate (AC14, B7, C1)."""

from __future__ import annotations

import random

import pytest

from vidgen.domain.stats import StatusCounts, eta_seconds, success_rate
from vidgen.domain.status import RowStatus

R = RowStatus


def test_counts_from_statuses() -> None:
    """TT-AC14-P1."""
    counts = StatusCounts.from_statuses(
        [R.COMPLETED, R.COMPLETED, R.FAILED, R.QUEUED, R.PROCESSING, R.SKIPPED, R.CANCELLED]
    )
    assert (counts.total, counts.completed, counts.failed) == (7, 2, 1)
    assert (counts.queued, counts.processing, counts.skipped, counts.cancelled) == (1, 1, 1, 1)
    assert counts.is_consistent


def test_empty_batch_counts_are_zero_and_consistent() -> None:
    """TT-AC14-E2 / E1 boundary."""
    counts = StatusCounts.from_statuses([])
    assert counts.total == 0
    assert counts.is_consistent


def test_all_skipped_batch() -> None:
    """TT-AC14-E2."""
    counts = StatusCounts.from_statuses([R.SKIPPED] * 5)
    assert counts.skipped == 5
    assert counts.remaining == 0
    assert counts.is_consistent


def test_remaining_is_queued_plus_processing() -> None:
    """C1."""
    counts = StatusCounts.from_statuses([R.QUEUED, R.QUEUED, R.PROCESSING, R.COMPLETED, R.FAILED])
    assert counts.remaining == 3


def test_manually_built_inconsistent_counts_are_detected() -> None:
    """TT-AC14-P1: the invariant check can actually fail."""
    bad = StatusCounts(
        total=10, completed=3, processing=1, queued=1, failed=1, skipped=1, cancelled=1
    )
    assert not bad.is_consistent


def test_counts_always_add_up_for_random_status_mixes() -> None:
    """TT-AC14-E3: property-style, fixed seed."""
    rng = random.Random(1018)  # noqa: S311 - deterministic test data
    for _ in range(300):
        statuses = [rng.choice(list(R)) for _ in range(rng.randint(0, 200))]
        counts = StatusCounts.from_statuses(statuses)
        assert counts.total == len(statuses)
        assert counts.is_consistent


def test_eta_is_remaining_times_mean_of_recent_render_times() -> None:
    """TT-AC14-P2 (B7)."""
    assert eta_seconds(remaining=10, recent_render_seconds=[2.0, 4.0]) == pytest.approx(30.0)


def test_eta_uses_only_the_last_twenty_completed_rows() -> None:
    """TT-AC14-P2: 25 durations, the first five (100 s) must be ignored."""
    durations = [100.0] * 5 + [2.0] * 20
    assert eta_seconds(remaining=3, recent_render_seconds=durations) == pytest.approx(6.0)


def test_eta_with_fewer_than_twenty_uses_all_available() -> None:
    """TT-AC14-E11."""
    assert eta_seconds(remaining=2, recent_render_seconds=[3.0]) == pytest.approx(6.0)


def test_eta_is_none_until_the_first_row_completes() -> None:
    """TT-AC14-E1, E11."""
    assert eta_seconds(remaining=10, recent_render_seconds=[]) is None


def test_eta_is_zero_when_nothing_remains() -> None:
    """TT-AC14-E11."""
    assert eta_seconds(remaining=0, recent_render_seconds=[2.0]) == 0.0


def test_success_rate_is_completed_over_completed_plus_failed() -> None:
    """TT-AC14-P5 (B7)."""
    assert success_rate(completed=9, failed=1) == pytest.approx(0.9)
    assert success_rate(completed=0, failed=4) == 0.0
    assert success_rate(completed=4, failed=0) == 1.0


def test_success_rate_is_none_without_completed_or_failed_rows() -> None:
    """TT-AC14-E1: no division by zero."""
    assert success_rate(completed=0, failed=0) is None
