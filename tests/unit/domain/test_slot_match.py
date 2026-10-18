"""Target-word match and manual slot validation (AC6, C3). Cases TT-AC6-*."""

from __future__ import annotations

import math

import pytest

from vidgen.domain.codes import FailureCode
from vidgen.domain.slot_match import InvalidSlotError, select_target_word, validate_slot
from vidgen.domain.values import Word

THRESHOLD = 0.6


def w(text: str, start: float, conf: float) -> Word:
    """Build a Word lasting 0.4 s."""
    return Word(text=text, start_s=start, end_s=start + 0.4, confidence=conf)


def test_high_confidence_match_is_returned_with_its_timestamps() -> None:
    """TT-AC6-P1."""
    words = [w("namaste", 0.0, 0.9), w("ji", 1.0, 0.95), w("aap", 2.0, 0.9)]
    found = select_target_word(words, "ji", THRESHOLD)
    assert found is not None
    assert (found.start_s, found.end_s) == (1.0, 1.4)


def test_match_ignores_case_and_surrounding_punctuation() -> None:
    """TT-AC6-P1."""
    assert select_target_word([w("Ji,", 1.0, 0.9)], "ji", THRESHOLD) is not None


def test_confidence_below_threshold_means_not_found() -> None:
    """TT-AC6-N1."""
    assert select_target_word([w("ji", 1.0, 0.59)], "ji", THRESHOLD) is None


def test_confidence_exactly_at_threshold_counts_as_found() -> None:
    """TT-AC6-E3 (C3): inclusive."""
    assert select_target_word([w("ji", 1.0, 0.6)], "ji", THRESHOLD) is not None


def test_word_absent_means_not_found() -> None:
    """TT-AC6-N2."""
    assert select_target_word([w("namaste", 0.0, 0.9)], "ji", THRESHOLD) is None


def test_empty_transcript_means_not_found() -> None:
    """TT-AC6-N2, E4."""
    assert select_target_word([], "ji", THRESHOLD) is None


def test_several_matches_pick_highest_confidence() -> None:
    """TT-AC6-E2 (C3)."""
    words = [w("ji", 1.0, 0.7), w("ji", 5.0, 0.95), w("ji", 9.0, 0.8)]
    found = select_target_word(words, "ji", THRESHOLD)
    assert found is not None
    assert found.start_s == 5.0


def test_equal_confidence_picks_the_earliest() -> None:
    """TT-AC6-E2 (C3)."""
    words = [w("ji", 9.0, 0.9), w("ji", 1.0, 0.9), w("ji", 5.0, 0.9)]
    found = select_target_word(words, "ji", THRESHOLD)
    assert found is not None
    assert found.start_s == 1.0


def test_low_confidence_matches_are_ignored_when_another_passes() -> None:
    """TT-AC6-E2."""
    words = [w("ji", 1.0, 0.3), w("ji", 4.0, 0.7)]
    found = select_target_word(words, "ji", THRESHOLD)
    assert found is not None
    assert found.start_s == 4.0


def test_devanagari_target_word_matches() -> None:
    """TT-AC6-P1."""
    word = w("\u091c\u0940", 1.0, 0.9)
    assert select_target_word([word], "\u091c\u0940", THRESHOLD) == word


# ---- manual slot ----------------------------------------------------------------------


def test_slot_inside_duration_is_accepted() -> None:
    """TT-AC6-P2."""
    validate_slot(1.0, 1.6, duration_s=4.0)


def test_slot_covering_the_whole_video_is_accepted() -> None:
    """TT-AC6-E1."""
    validate_slot(0.0, 4.0, duration_s=4.0)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (1.0, 4.001),  # TT-AC6-N3
        (2.0, 2.0),  # TT-AC6-E1 zero length
        (2.0, 1.0),  # TT-AC6-N4
        (-0.1, 1.0),
        (math.nan, 1.0),
        (1.0, math.inf),
        (-math.inf, 1.0),
    ],
)
def test_invalid_slots_are_rejected(start: float, end: float) -> None:
    """TT-AC6-N3, N4, E1."""
    with pytest.raises(InvalidSlotError) as info:
        validate_slot(start, end, duration_s=4.0)
    assert info.value.code is FailureCode.SLOT_NOT_FOUND
