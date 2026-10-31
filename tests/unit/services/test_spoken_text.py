"""The spoken suffix after a name (DD-39): ``spoken_text(name, suffix)`` is a pure function.

CONTRACT
  Both arguments are stripped. An empty suffix returns the name unchanged. If the last word
  of the name equals the suffix (str.casefold), the name is returned unchanged. Otherwise the
  result is "<name> <suffix>" with exactly one space. An empty name returns "".

Test tree IDs: SS-F-* (function), see docs/test-tree/spoken-suffix.md.
"""

from __future__ import annotations

import pytest

from tests.fixtures.names import (
    CONJUNCT_WITH_ZWJ,
    CONJUNCT_WITH_ZWNJ,
    DEVANAGARI_NAME,
    LATIN_40,
    ZWJ,
)
from vidgen.services.spoken_text import spoken_text

SUFFIX = "जी"  # the honorific "ji" in Devanagari, as the Admin types it
ARABIC_NAME = "أحمد"  # RTL letters, written as code points


# ---- positive: the suffix is added after the name -------------------------------------


def test_suffix_is_added_after_a_roman_name() -> None:
    """SS-F-P1: the Roman name gets the suffix after one space."""
    assert spoken_text("Asha Verma", SUFFIX) == f"Asha Verma {SUFFIX}"


def test_suffix_is_added_after_a_devanagari_name() -> None:
    """SS-F-P2: a Devanagari name gets the Devanagari suffix."""
    assert spoken_text(DEVANAGARI_NAME, SUFFIX) == f"{DEVANAGARI_NAME} {SUFFIX}"


def test_title_stays_and_the_suffix_follows_the_name() -> None:
    """SS-F-P3: a title is kept in front; the suffix goes last."""
    assert spoken_text("Smt. Asha Verma", SUFFIX) == f"Smt. Asha Verma {SUFFIX}"


def test_suffix_is_added_after_a_single_word_name() -> None:
    """SS-F-P4: a one-word name is a valid last word."""
    assert spoken_text("Asha", SUFFIX) == f"Asha {SUFFIX}"


def test_a_roman_suffix_is_added_as_typed() -> None:
    """SS-F-P5: the suffix is not translated or changed; a Roman one works too."""
    assert spoken_text("Asha Verma", "Ji") == "Asha Verma Ji"


# ---- negative: nothing is added, or nothing is doubled --------------------------------


def test_empty_suffix_leaves_the_name_unchanged() -> None:
    """SS-F-N1: an empty suffix switches the feature off."""
    assert spoken_text("Asha Verma", "") == "Asha Verma"


def test_whitespace_only_suffix_counts_as_empty() -> None:
    """SS-F-N2: a suffix of only spaces is stripped to nothing."""
    assert spoken_text("Asha Verma", "   ") == "Asha Verma"


def test_name_already_ending_with_the_suffix_is_not_doubled() -> None:
    """SS-F-N3: the last word equals the suffix, so nothing is added."""
    assert spoken_text(f"Asha {SUFFIX}", SUFFIX) == f"Asha {SUFFIX}"


@pytest.mark.parametrize(
    ("name", "suffix"),
    [("Asha ji", "Ji"), ("Asha JI", "ji"), ("Asha Ji", "JI"), ("Asha ji", "ji")],
)
def test_roman_suffix_is_not_doubled_in_any_case(name: str, suffix: str) -> None:
    """SS-F-N4: the comparison ignores case (str.casefold)."""
    assert spoken_text(name, suffix) == name


def test_a_middle_word_equal_to_the_suffix_does_not_stop_the_suffix() -> None:
    """SS-F-N5: only the LAST word counts, so the suffix is still added."""
    assert spoken_text(f"{SUFFIX} Asha Verma", SUFFIX) == f"{SUFFIX} Asha Verma {SUFFIX}"


def test_a_roman_middle_word_equal_to_the_suffix_does_not_stop_the_suffix() -> None:
    """SS-F-N5 (Roman): the same rule with a Roman suffix in the middle."""
    assert spoken_text("Ji Asha Verma", "ji") == "Ji Asha Verma ji"


@pytest.mark.parametrize(
    ("name", "suffix"),
    [
        ("Amitजी", SUFFIX),  # the name ends with the letters, inside one word
        ("Amitji", "ji"),
    ],
)
def test_a_name_that_only_ends_with_the_suffix_letters_gets_the_suffix(
    name: str, suffix: str
) -> None:
    """SS-F-N6: 'Amitji' is one word, not the word 'ji'; the suffix is added."""
    assert spoken_text(name, suffix) == f"{name} {suffix}"


# ---- edge: whitespace, empty names, joiners, long and unusual text --------------------


def test_whitespace_around_both_arguments_is_stripped() -> None:
    """SS-F-E1: spaces, tabs and newlines around the name and the suffix are removed."""
    assert spoken_text("  Asha Verma  ", f"  {SUFFIX}  ") == f"Asha Verma {SUFFIX}"
    assert spoken_text("\tAsha Verma\n", SUFFIX) == f"Asha Verma {SUFFIX}"


def test_the_result_has_exactly_one_space_before_the_suffix() -> None:
    """SS-F-E2: a name with trailing spaces does not produce a double space."""
    result = spoken_text("Asha Verma   ", SUFFIX)
    assert result == f"Asha Verma {SUFFIX}"
    assert "  " not in result


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_empty_name_returns_an_empty_string(name: str) -> None:
    """SS-F-E3: nothing to say, so the suffix is not spoken alone."""
    assert spoken_text(name, SUFFIX) == ""


def test_empty_name_and_empty_suffix_return_an_empty_string() -> None:
    """SS-F-E3: both empty."""
    assert spoken_text("", "") == ""


def test_a_name_equal_to_the_suffix_is_returned_unchanged() -> None:
    """SS-F-E4: the name is itself the last word that equals the suffix."""
    assert spoken_text(SUFFIX, SUFFIX) == SUFFIX


@pytest.mark.parametrize("joiner", [CONJUNCT_WITH_ZWJ, CONJUNCT_WITH_ZWNJ])
def test_zero_width_joiners_inside_the_name_are_kept(joiner: str) -> None:
    """SS-F-E5: ZWJ and ZWNJ are part of the spelling and are never removed."""
    result = spoken_text(f"{joiner} Verma", SUFFIX)
    assert result == f"{joiner} Verma {SUFFIX}"


def test_a_joiner_at_the_end_of_the_name_is_kept() -> None:
    """SS-F-E5: a name ending with a joiner is not treated as ending with the suffix."""
    assert spoken_text(f"Asha{ZWJ}", SUFFIX) == f"Asha{ZWJ} {SUFFIX}"


def test_emoji_in_the_name_is_passed_through() -> None:
    """SS-F-E6: symbols in a name are kept as they are."""
    assert spoken_text("Asha \U0001f600", SUFFIX) == f"Asha \U0001f600 {SUFFIX}"


def test_rtl_name_gets_the_suffix_after_it() -> None:
    """SS-F-E6: right-to-left letters keep their order; the suffix comes last."""
    assert spoken_text(ARABIC_NAME, SUFFIX) == f"{ARABIC_NAME} {SUFFIX}"


def test_a_forty_grapheme_name_gets_the_suffix() -> None:
    """SS-F-E7: the longest name the app accepts still gets the suffix."""
    assert spoken_text(LATIN_40, SUFFIX) == f"{LATIN_40} {SUFFIX}"


@pytest.mark.parametrize("name", ["Asha Verma", f"Asha {SUFFIX}", DEVANAGARI_NAME])
def test_applying_the_function_twice_adds_the_suffix_once(name: str) -> None:
    """SS-F-E8: the output is stable; a second pass changes nothing."""
    once = spoken_text(name, SUFFIX)
    assert spoken_text(once, SUFFIX) == once


# ---- multi-word suffix (coordinator decision, DD-39) -----------------------------------


def test_multi_word_suffix_already_at_the_end_is_not_doubled() -> None:
    """SS-F-N7: the last words of the name equal the suffix words; nothing is added."""
    assert spoken_text("Amit ji sahab", "ji sahab") == "Amit ji sahab"


def test_multi_word_suffix_match_ignores_case() -> None:
    """SS-F-N7: the word comparison uses casefold."""
    assert spoken_text("Amit JI Sahab", "ji sahab") == "Amit JI Sahab"


def test_only_one_word_of_a_multi_word_suffix_at_the_end_is_not_a_match() -> None:
    """SS-F-N8: the last two words are 'Amit ji', not 'ji sahab', so the suffix is added."""
    assert spoken_text("Amit ji", "ji sahab") == "Amit ji ji sahab"


def test_multi_word_suffix_is_added_to_a_one_word_name() -> None:
    """SS-F-P6: a one-word name gets the whole multi-word suffix after it."""
    assert spoken_text("Amit", "ji sahab") == "Amit ji sahab"


def test_multi_word_match_with_extra_spaces_inside_the_name_is_not_doubled() -> None:
    """SS-F-E10: the words are compared after splitting, so inner spacing does not matter."""
    assert spoken_text("Amit  ji   sahab", "ji sahab") == "Amit  ji   sahab"


# ---- spacing inside the name (coordinator decision, DD-39) -----------------------------


def test_repeated_spaces_inside_the_name_are_kept() -> None:
    """SS-F-E9: only the ends of the name are stripped; inner spacing is not changed."""
    assert spoken_text("Amit  Kumar", SUFFIX) == f"Amit  Kumar {SUFFIX}"
