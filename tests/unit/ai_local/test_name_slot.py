"""AC4: the name slot is found in the transcript; the manual slot is the fallback."""

from __future__ import annotations

import pytest

from vidgen.domain.values import Word
from vidgen.infrastructure.local_ai.errors import NameSlotNotFoundError
from vidgen.infrastructure.local_ai.name_slot import detect_name_slot

PLACEHOLDER = "Krishan"


def w(text: str, start: float, end: float, conf: float = 0.9) -> Word:
    """A transcript word."""
    return Word(text=text, start_s=start, end_s=end, confidence=conf)


def test_slot_is_found_from_the_placeholder_word() -> None:
    words = [w("Krishan", 0.0, 0.8), w("ji", 0.8, 1.0), w("Ram", 1.0, 1.3)]
    slot = detect_name_slot(words, PLACEHOLDER)
    assert (slot.start_s, slot.end_s) == (0.0, 0.8)
    assert slot.source == "auto"
    assert slot.ambiguous is False


@pytest.mark.parametrize("spelled", ["krishan", "KRISHAN", "Krishan,", "Krishan."])
def test_match_ignores_case_and_punctuation(spelled: str) -> None:
    slot = detect_name_slot([w(spelled, 0.2, 0.9)], PLACEHOLDER)
    assert slot.source == "auto"


def test_not_found_falls_back_to_the_manual_slot() -> None:
    words = [w("hello", 0.0, 0.5), w("friends", 0.5, 1.0)]
    slot = detect_name_slot(words, PLACEHOLDER, manual=(0.1, 0.9))
    assert (slot.start_s, slot.end_s) == (0.1, 0.9)
    assert slot.source == "manual"


def test_not_found_and_no_manual_slot_is_a_clear_error() -> None:
    with pytest.raises(NameSlotNotFoundError):
        detect_name_slot([w("hello", 0.0, 0.5)], PLACEHOLDER)


def test_empty_transcript_uses_manual_or_errors() -> None:
    assert detect_name_slot([], PLACEHOLDER, manual=(0.0, 1.0)).source == "manual"
    with pytest.raises(NameSlotNotFoundError):
        detect_name_slot([], PLACEHOLDER)


def test_two_hits_choose_the_first_and_flag_for_human_review() -> None:
    words = [w("Krishan", 0.0, 0.8), w("ji", 0.8, 1.0), w("Krishan", 5.0, 5.8)]
    slot = detect_name_slot(words, PLACEHOLDER)
    assert (slot.start_s, slot.end_s) == (0.0, 0.8)
    assert slot.ambiguous is True


def test_manual_slot_wins_over_two_hits_when_given() -> None:
    words = [w("Krishan", 0.0, 0.8), w("Krishan", 5.0, 5.8)]
    slot = detect_name_slot(words, PLACEHOLDER, manual=(5.0, 5.8))
    assert (slot.start_s, slot.end_s) == (5.0, 5.8)
    assert slot.source == "manual"


def test_low_confidence_hit_is_still_flagged_ambiguous() -> None:
    slot = detect_name_slot([w("Krishan", 0.0, 0.8, conf=0.2)], PLACEHOLDER, min_confidence=0.6)
    assert slot.ambiguous is True


def test_inverted_manual_slot_is_rejected() -> None:
    with pytest.raises(ValueError):
        detect_name_slot([], PLACEHOLDER, manual=(2.0, 1.0))
