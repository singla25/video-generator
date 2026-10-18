"""Content lock: only the confirmed slot may change (AC18, C6)."""

from __future__ import annotations

import pytest

from vidgen.domain.codes import FailureCode
from vidgen.domain.slot_match import ContentLockViolationError, ensure_within_slot

SLOT = (1.0, 1.6)


def test_ranges_inside_the_slot_are_allowed() -> None:
    """TT-AC18-P1."""
    ensure_within_slot(SLOT, [(1.1, 1.5)])


def test_range_equal_to_the_slot_boundaries_is_allowed() -> None:
    """TT-AC18-E1."""
    ensure_within_slot(SLOT, [(1.0, 1.6)])


def test_extension_region_after_the_slot_is_allowed_when_declared() -> None:
    """TT-AC18-P1: the video grows by at most the planned extension."""
    ensure_within_slot(SLOT, [(1.0, 2.0)], extension_s=0.4)


@pytest.mark.parametrize("rng", [(0.5, 1.2), (1.2, 2.0), (0.0, 5.0), (0.999, 1.2), (1.2, 1.601)])
def test_range_outside_the_slot_is_a_content_lock_violation(rng: tuple[float, float]) -> None:
    """TT-AC18-N1, E2: even 1 ms outside is rejected."""
    with pytest.raises(ContentLockViolationError) as info:
        ensure_within_slot(SLOT, [rng])
    assert info.value.code is FailureCode.CONTENT_LOCK_VIOLATION


def test_one_bad_range_rejects_the_whole_plan() -> None:
    """TT-AC18-E3."""
    with pytest.raises(ContentLockViolationError):
        ensure_within_slot(SLOT, [(1.1, 1.2), (3.0, 3.5)])


def test_extension_beyond_the_declared_amount_is_rejected() -> None:
    """TT-AC18-N1."""
    with pytest.raises(ContentLockViolationError):
        ensure_within_slot(SLOT, [(1.0, 2.1)], extension_s=0.4)


def test_empty_range_list_is_allowed() -> None:
    """TT-AC18-E3."""
    ensure_within_slot(SLOT, [])
