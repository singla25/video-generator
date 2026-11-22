"""``sound_key`` and ``closeness``: sound-alike matching across Roman and Devanagari (AC1)."""

from __future__ import annotations

import time

import pytest

from tests.unit.name_detection.name_pairs import MATCHING_PAIRS, UNRELATED_PAIRS
from vidgen.domain.name_match import closeness, sound_key

DEFAULT_CLOSENESS = 0.8


# ---- positive -------------------------------------------------------------------------


@pytest.mark.parametrize("heard", ["कृष्ण", "किशन", "krishan", "Krishn", "Kishan"])
def test_krishan_is_close_to_its_spoken_variants(heard: str) -> None:
    assert closeness("Krishan", heard) >= DEFAULT_CLOSENESS


def test_identical_text_has_closeness_one() -> None:
    assert closeness("Krishan", "Krishan") == 1.0


def test_equal_sound_keys_give_closeness_one() -> None:
    assert sound_key("Vijay") == sound_key("Wijay")
    assert closeness("Vijay", "Wijay") == 1.0


def test_labelled_pairs_match_at_ninety_percent_or_better() -> None:
    hits = [p for p in MATCHING_PAIRS if closeness(*p) >= DEFAULT_CLOSENESS]
    misses = [p for p in MATCHING_PAIRS if p not in hits]
    assert len(MATCHING_PAIRS) >= 20
    assert len(hits) / len(MATCHING_PAIRS) >= 0.9, f"missed: {misses}"


def test_sound_key_is_a_string_and_is_deterministic() -> None:
    first = sound_key("कृष्ण")
    assert isinstance(first, str) and first != ""
    assert all(sound_key("कृष्ण") == first for _ in range(5))


@pytest.mark.parametrize(
    ("a", "b"),
    [("KRISHAN", "krishan"), ("Krishan", "krishan"), ("Krishan!", "Krishan"), ("कृष्ण।", "कृष्ण")],
)
def test_case_and_punctuation_do_not_change_the_key(a: str, b: str) -> None:
    assert sound_key(a) == sound_key(b)


def test_repeated_letters_are_smoothed() -> None:
    assert closeness("Anil", "Annil") == 1.0
    assert closeness("Krishan", "Krisshan") == 1.0


def test_zero_width_joiner_is_ignored() -> None:
    assert sound_key("कृ‍ष्ण") == sound_key("कृष्ण")
    assert sound_key("कृ‌ष्ण") == sound_key("कृष्ण")


def test_text_is_normalised_to_nfc() -> None:
    # nukta written as one code point vs base + nukta
    assert sound_key("फ़रहान") == sound_key("फ़रहान")


def test_nukta_and_chandrabindu_do_not_change_closeness() -> None:
    assert closeness("फरहान", "फ़रहान") >= DEFAULT_CLOSENESS
    assert closeness("हंस", "हँस") >= DEFAULT_CLOSENESS


def test_mixed_script_word_is_comparable() -> None:
    assert closeness("Krisha" + "ण", "Krishan") >= DEFAULT_CLOSENESS


# ---- negative -------------------------------------------------------------------------


def test_ramesh_is_far_from_krishan() -> None:
    assert closeness("Krishan", "Ramesh") < 0.5


@pytest.mark.parametrize(("typed", "heard"), UNRELATED_PAIRS)
def test_unrelated_names_stay_below_the_default_closeness(typed: str, heard: str) -> None:
    assert closeness(typed, heard) < DEFAULT_CLOSENESS


@pytest.mark.parametrize("text", ["", "   ", "!!!", "...", "।", "‍", "‍‌"])
def test_empty_or_punctuation_only_text_has_an_empty_key(text: str) -> None:
    assert sound_key(text) == ""


@pytest.mark.parametrize("empty", ["", "!!!", "\u200d"])
def test_closeness_is_zero_when_either_key_is_empty(empty: str) -> None:
    assert closeness(empty, "Krishan") == 0.0
    assert closeness("Krishan", empty) == 0.0
    assert closeness(empty, empty) == 0.0


# ---- edge -----------------------------------------------------------------------------


def test_one_letter_text_does_not_crash_and_is_in_range() -> None:
    assert 0.0 <= closeness("K", "Krishan") <= 1.0
    assert 0.0 <= closeness("क", "K") <= 1.0


def test_digits_do_not_crash_and_stay_in_range() -> None:
    assert isinstance(sound_key("123"), str)
    assert 0.0 <= closeness("Krishan2", "Krishan") <= 1.0
    assert 0.0 <= closeness("123", "456") <= 1.0


@pytest.mark.xdist_group("timing")
def test_two_hundred_character_input_is_fast_and_exact() -> None:
    long_text = ("Krishan" * 30)[:200]
    start = time.perf_counter()
    assert closeness(long_text, long_text) == 1.0
    assert 0.0 <= closeness(long_text, "Ramesh") <= 1.0
    assert time.perf_counter() - start < 2.0  # generous: xdist workers share the CPU


@pytest.mark.parametrize(("a", "b"), [*MATCHING_PAIRS[:10], *UNRELATED_PAIRS[:5]])
def test_closeness_is_symmetric_and_in_range(a: str, b: str) -> None:
    assert closeness(a, b) == closeness(b, a)
    assert 0.0 <= closeness(a, b) <= 1.0


def test_emoji_and_rtl_text_do_not_crash() -> None:
    for text in ["Krishan 🎬", "كريشان", "שלום", "\U0001f600"]:
        assert isinstance(sound_key(text), str)
        assert 0.0 <= closeness(text, "Krishan") <= 1.0
