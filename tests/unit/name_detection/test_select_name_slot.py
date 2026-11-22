"""``select_name_slot``: accept rule (closeness AND confidence) and the closest candidates."""

from __future__ import annotations

import math
import time

import pytest

from vidgen.domain.name_match import (
    MIN_CANDIDATE_CLOSENESS,
    NameMatch,
    ScoredWord,
    closeness,
    select_name_slot,
)
from vidgen.domain.values import Word

CONF = 0.6
CLOSE = 0.8


def w(text: str, start: float, conf: float = 0.9) -> Word:
    """A 0.4 s word."""
    return Word(text=text, start_s=start, end_s=start + 0.4, confidence=conf)


def pick(words: list[Word], target: str = "Krishan", **kw: float) -> NameMatch:
    kw.setdefault("confidence_threshold", CONF)
    kw.setdefault("closeness_threshold", CLOSE)
    return select_name_slot(words, target, **kw)  # type: ignore[arg-type]


def texts(match: NameMatch) -> list[str]:
    return [c.word.text for c in match.candidates]


# ---- positive -------------------------------------------------------------------------


def test_minimum_candidate_closeness_is_point_four() -> None:
    assert MIN_CANDIDATE_CLOSENESS == 0.4


def test_exact_word_is_found_with_no_candidates() -> None:
    match = pick([w("namaste", 0.0), w("Krishan", 1.0), w("ji", 2.0)])
    assert match.found == w("Krishan", 1.0)
    assert match.candidates == ()


@pytest.mark.parametrize("heard", ["कृष्ण", "किशन", "krishan", "Krishn"])
def test_sound_alike_word_in_either_script_is_found(heard: str) -> None:
    assert pick([w(heard, 1.5)]).found == w(heard, 1.5)


def test_best_closeness_wins_over_higher_confidence() -> None:
    near, exact = w("Kishan", 1.0, 0.99), w("Krishan", 2.0, 0.65)
    assert closeness("Krishan", "Kishan") < 1.0
    assert pick([near, exact]).found == exact


def test_equal_closeness_prefers_higher_confidence_then_earlier_start() -> None:
    assert pick([w("Krishan", 1.0, 0.7), w("krishan", 2.0, 0.9)]).found == w("krishan", 2.0, 0.9)
    assert pick([w("Krishan", 5.0, 0.9), w("Krishan", 2.0, 0.9)]).found == w("Krishan", 2.0, 0.9)


def test_duplicate_identical_words_are_found_once() -> None:
    word = w("Krishan", 1.0)
    match = pick([word, word])
    assert match.found == word and match.candidates == ()


def test_close_but_low_confidence_is_a_candidate_not_a_match() -> None:
    match = pick([w("Krishan", 1.0, 0.3)])
    assert match.found is None
    assert texts(match) == ["Krishan"]
    assert isinstance(match.candidates[0], ScoredWord)
    assert match.candidates[0].closeness == 1.0
    assert match.candidates[0].word.confidence == 0.3


def test_candidates_are_best_first_with_closeness_then_confidence_then_start() -> None:
    words = [
        w("Krishn", 4.0, 0.2),
        w("Zzzz", 0.5, 0.9),
        w("Krishan", 3.0, 0.5),
        w("krishan", 1.0, 0.5),
        w("Krishan", 2.0, 0.55),
    ]
    match = pick(words)
    assert match.found is None
    starts = [c.word.start_s for c in match.candidates]
    assert starts[:3] == [2.0, 1.0, 3.0]
    assert len(match.candidates) == 3
    scores = [c.closeness for c in match.candidates]
    assert scores == sorted(scores, reverse=True)


def test_candidates_are_limited_by_max_candidates() -> None:
    words = [w("Krishan", float(i), 0.1) for i in range(6)]
    assert len(pick(words).candidates) == 3
    assert len(pick(words, max_candidates=1).candidates) == 1  # type: ignore[arg-type]
    assert len(pick(words, max_candidates=5).candidates) == 5  # type: ignore[arg-type]


def test_every_candidate_is_at_least_the_minimum_closeness() -> None:
    match = pick([w("Krishan", 1.0, 0.1), w("Zzzz", 2.0, 0.1), w("Kishan", 3.0, 0.1)])
    assert all(c.closeness >= MIN_CANDIDATE_CLOSENESS for c in match.candidates)
    assert "Zzzz" not in texts(match)


# ---- negative -------------------------------------------------------------------------


def test_confident_but_far_word_is_nothing() -> None:
    match = pick([w("Zzzz", 1.0, 0.99), w("Ramesh", 2.0, 0.99)])
    assert match.found is None and match.candidates == ()


def test_empty_word_list_is_not_found_without_error() -> None:
    assert pick([]) == NameMatch(found=None, candidates=())


@pytest.mark.parametrize("target", ["", "   ", "!!!", "।", "‍"])
def test_empty_or_punctuation_only_target_finds_nothing(target: str) -> None:
    match = pick([w("Krishan", 1.0), w("!!!", 2.0)], target=target)
    assert match == NameMatch(found=None, candidates=())


def test_words_with_empty_sound_are_never_chosen() -> None:
    match = pick([w("...", 1.0), w("", 2.0)])
    assert match == NameMatch(found=None, candidates=())


def test_short_target_needs_an_exact_sound_match_and_gives_no_candidates() -> None:
    assert pick([w("Ak", 1.0)], target="Ab").found is None
    assert pick([w("Ak", 1.0)], target="Ab").candidates == ()
    assert pick([w("Ab", 1.0)], target="Ab").found == w("Ab", 1.0)


def test_short_target_low_confidence_gives_no_candidates() -> None:
    assert pick([w("Ab", 1.0, 0.1)], target="Ab") == NameMatch(found=None, candidates=())


# ---- edge -----------------------------------------------------------------------------


def test_confidence_exactly_at_the_limit_is_accepted_and_just_below_is_not() -> None:
    assert pick([w("Krishan", 1.0, CONF)]).found is not None
    assert pick([w("Krishan", 1.0, math.nextafter(CONF, 0))]).found is None


def test_closeness_exactly_at_the_limit_is_accepted_and_just_above_is_not() -> None:
    heard = "Kishan"
    exact = closeness("Krishan", heard)
    assert 0.0 < exact < 1.0
    assert pick([w(heard, 1.0)], closeness_threshold=exact).found is not None
    above = math.nextafter(exact, 1.0)
    miss = pick([w(heard, 1.0)], closeness_threshold=above)
    assert miss.found is None and texts(miss) == [heard]


def test_fewer_than_three_words_give_fewer_candidates() -> None:
    assert len(pick([w("Krishan", 1.0, 0.1)]).candidates) == 1
    assert len(pick([w("Krishan", 1.0, 0.1), w("Krishn", 2.0, 0.1)]).candidates) == 2


def test_candidates_hold_the_same_word_twice_when_heard_twice() -> None:
    words = [w("Krishan", 1.0, 0.1), w("Krishan", 3.0, 0.1)]
    assert [c.word.start_s for c in pick(words).candidates] == [1.0, 3.0]


def test_hundred_words_pick_the_right_one() -> None:
    words = [w("Zzzz" if i != 57 else "किशन", i * 0.5) for i in range(100)]
    assert pick(words).found == w("किशन", 28.5)


@pytest.mark.xdist_group("timing")
def test_two_thousand_words_are_matched_quickly() -> None:
    words = [w(f"word{i % 7}", i * 0.3, 0.8) for i in range(2000)]
    words[1500] = w("Krishan", 450.0)
    start = time.perf_counter()
    match = pick(words)
    assert time.perf_counter() - start < 2.0  # generous: xdist workers share the CPU
    assert match.found == w("Krishan", 450.0)


def test_result_types_are_frozen() -> None:
    match = pick([w("Krishan", 1.0, 0.1)])
    with pytest.raises(AttributeError):
        match.found = None  # type: ignore[misc]
    with pytest.raises(AttributeError):
        match.candidates[0].closeness = 0.0  # type: ignore[misc]


def test_selection_is_deterministic() -> None:
    words = [w("Krishan", 1.0, 0.1), w("Kishan", 2.0, 0.1), w("Krishn", 3.0, 0.1)]
    assert pick(words) == pick(list(words))
