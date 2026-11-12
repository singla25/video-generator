"""Several name slots per template: the rules that apply to the set together (DD-40).

Test IDs: MS-VS-* in docs/test-tree/multi-slot-model.md.
Gap values are chosen so that the float subtraction is exact enough for the 0.2 s rule
(2.2 - 2.0 >= 0.2 holds in binary floats; 1.8 - 1.6 does not, so it is not used as a boundary).
"""

from __future__ import annotations

import math

import pytest

from vidgen.domain.codes import DomainError, FailureCode, plain_message
from vidgen.domain.slot_match import InvalidSlotError, validate_slot, validate_slots

DURATION_S = 4.0
LONG_DURATION_S = 10.0
MAX_SLOTS = 5


# ---- positive -------------------------------------------------------------------------


def test_two_slots_inside_the_video_are_accepted() -> None:
    """MS-VS-P1."""
    validate_slots([(0.0, 1.0), (2.0, 3.0)], DURATION_S)


def test_three_slots_are_accepted() -> None:
    """MS-VS-P2."""
    validate_slots([(0.0, 0.5), (1.5, 2.0), (3.0, 3.5)], DURATION_S)


def test_exactly_the_maximum_of_five_slots_is_accepted() -> None:
    """MS-VS-P3: five is allowed, half a second apart."""
    slots = [(0.0, 0.4), (0.9, 1.3), (1.8, 2.2), (2.7, 3.1), (3.6, 4.0)]
    assert len(slots) == MAX_SLOTS
    validate_slots(slots, DURATION_S)


def test_gap_of_exactly_point_two_seconds_is_accepted() -> None:
    """MS-VS-P4, MS-VS-E3: next.start - previous.end == 0.2 is the smallest allowed gap."""
    validate_slots([(1.0, 2.0), (2.2, 2.8)], DURATION_S)


def test_a_single_valid_slot_is_accepted() -> None:
    """MS-VS-P5."""
    validate_slots([(1.0, 1.6)], DURATION_S)


def test_slots_given_unsorted_are_accepted_when_fine_once_sorted() -> None:
    """MS-VS-P6: the order of the input does not matter."""
    validate_slots([(2.5, 3.0), (0.0, 1.0), (1.5, 2.0)], DURATION_S)


# ---- negative -------------------------------------------------------------------------


def test_six_slots_are_refused_with_slots_invalid() -> None:
    """MS-VS-N1: each slot is fine on its own; the count is the problem."""
    slots = [(float(n), n + 0.5) for n in range(6)]
    with pytest.raises(DomainError) as info:
        validate_slots(slots, LONG_DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


def test_gap_of_point_nineteen_seconds_is_refused_with_slots_invalid() -> None:
    """MS-VS-N2, MS-VS-E3: just under the minimum gap."""
    with pytest.raises(DomainError) as info:
        validate_slots([(1.0, 2.0), (2.19, 3.0)], DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


def test_overlapping_slots_are_refused_with_slots_invalid() -> None:
    """MS-VS-N3."""
    with pytest.raises(DomainError) as info:
        validate_slots([(1.0, 2.0), (1.5, 2.5)], DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


def test_touching_slots_with_no_gap_are_refused_with_slots_invalid() -> None:
    """MS-VS-N4: a gap of 0 is below the 0.2 s minimum."""
    with pytest.raises(DomainError) as info:
        validate_slots([(1.0, 2.0), (2.0, 2.6)], DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


def test_overlap_that_appears_only_after_sorting_is_refused() -> None:
    """MS-VS-N5: the check runs on the sorted list, so a later-listed slot can collide."""
    with pytest.raises(DomainError) as info:
        validate_slots([(2.5, 3.0), (1.0, 2.6)], DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


def test_a_slot_beyond_the_duration_is_refused_by_the_single_slot_rule() -> None:
    """MS-VS-N6: validate_slot's rule applies to every slot; that error is not a set error."""
    with pytest.raises(InvalidSlotError) as info:
        validate_slots([(1.0, 1.6), (3.9, 4.1)], DURATION_S)
    assert info.value.code is FailureCode.SLOT_NOT_FOUND


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (1.0, 4.001),
        (2.0, 2.0),
        (2.0, 1.0),
        (-0.1, 1.0),
        (math.nan, 1.0),
        (1.0, math.inf),
    ],
)
def test_a_single_invalid_slot_fails_exactly_like_validate_slot(start: float, end: float) -> None:
    """MS-VS-N7, MS-VS-P5: one slot gets the same rules and the same error as validate_slot."""
    with pytest.raises(InvalidSlotError) as single:
        validate_slot(start, end, DURATION_S)
    with pytest.raises(InvalidSlotError) as as_set:
        validate_slots([(start, end)], DURATION_S)
    assert as_set.value.code is single.value.code is FailureCode.SLOT_NOT_FOUND


def test_five_slots_with_one_overlap_are_refused_with_slots_invalid() -> None:
    """MS-VS-N8: the maximum does not relax the overlap rule."""
    slots = [(0.0, 0.4), (0.9, 1.3), (1.8, 2.2), (2.7, 3.1), (3.0, 3.5)]
    with pytest.raises(DomainError) as info:
        validate_slots(slots, DURATION_S)
    assert info.value.code is FailureCode.SLOTS_INVALID


# ---- edge -----------------------------------------------------------------------------


def test_slots_message_says_they_overlap_or_are_too_close() -> None:
    """MS-VS-E1: the wording is fixed in the code table."""
    assert plain_message(FailureCode.SLOTS_INVALID) == ("The name slots overlap or are too close.")


def test_a_slot_ending_exactly_at_the_duration_is_accepted_in_a_set() -> None:
    """MS-VS-E2."""
    validate_slots([(0.0, 1.0), (3.0, DURATION_S)], DURATION_S)
