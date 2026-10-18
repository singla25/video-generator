"""Row validation (AC3, A1, A2, B1). Case IDs in each docstring."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from tests.fixtures import names as n
from vidgen.domain.codes import FailureCode
from vidgen.domain.validation import (
    RowInput,
    RowRules,
    RowValidator,
    RowVerdict,
    count_graphemes,
    effective_spoken_name,
    validate_rows,
)

RULES = RowRules(max_name_graphemes=40)


def check(
    name: str, id_: str = "ID1", spoken: str | None = None, rules: RowRules = RULES
) -> RowVerdict:
    """Validate one row with a fresh validator."""
    return RowValidator(rules).validate(RowInput(2, name, id_, spoken))


# ---- positive -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [n.LATIN_NAME, n.DEVANAGARI_NAME, n.PUNCTUATED_NAME, n.TITLED_MIXED_NAME, n.ACCENTED_NAME],
)
def test_valid_names_are_accepted(name: str) -> None:
    """TT-AC3-P1, P2, P3, P4."""
    verdict = check(name, "RJ12")
    assert verdict.valid
    assert verdict.code is None
    assert verdict.faults == ()


def test_first_of_two_rows_with_same_id_stays_valid() -> None:
    """TT-AC3-P5."""
    first, second = validate_rows([RowInput(2, "Asha", "A1"), RowInput(3, "Bina", "A1")], RULES)
    assert first.valid
    assert not second.valid


@pytest.mark.parametrize("name", [n.CONJUNCT_WITH_ZWJ, n.CONJUNCT_WITH_ZWNJ])
def test_zwj_and_zwnj_inside_devanagari_are_allowed(name: str) -> None:
    """TT-AC3-P7 (A1)."""
    assert check(name).valid


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_empty_name_gets_empty_name_code(name: str) -> None:
    """TT-AC3-N1."""
    verdict = check(name)
    assert verdict.code is FailureCode.INVALID_ROW_EMPTY_NAME
    assert not verdict.valid


@pytest.mark.parametrize("id_", ["", "  "])
def test_empty_id_gets_empty_id_code(id_: str) -> None:
    """TT-AC3-N2."""
    assert check("Asha", id_).code is FailureCode.INVALID_ROW_EMPTY_ID


def test_duplicate_id_names_the_earlier_row() -> None:
    """TT-AC3-N3."""
    rows = [RowInput(2, "Asha", "A1"), RowInput(5, "Bina", "A1")]
    _, second = validate_rows(rows, RULES)
    assert second.code is FailureCode.DUPLICATE_ID
    assert second.duplicate_of == 2
    assert "2" in second.message


def test_name_of_41_graphemes_is_too_long() -> None:
    """TT-AC3-N4."""
    assert check(n.LATIN_41).code is FailureCode.INVALID_ROW_NAME_TOO_LONG


@pytest.mark.parametrize("name", n.BAD_CHARACTER_NAMES)
def test_characters_outside_the_allowed_set_are_rejected(name: str) -> None:
    """TT-AC3-N5, N8, E7."""
    assert check(name).code is FailureCode.INVALID_ROW_BAD_CHARACTERS


def test_multi_fault_row_reports_primary_code_by_priority() -> None:
    """TT-AC3-N6 (B1): empty name > empty ID > bad chars > too long > duplicate."""
    assert check("", "").code is FailureCode.INVALID_ROW_EMPTY_NAME
    assert check("Asha", "").code is FailureCode.INVALID_ROW_EMPTY_ID
    assert check("@" * 41).code is FailureCode.INVALID_ROW_BAD_CHARACTERS
    assert check("@", "").code is FailureCode.INVALID_ROW_EMPTY_ID


def test_multi_fault_row_lists_every_fault_in_priority_order() -> None:
    """TT-AC3-E13 (B1)."""
    verdict = check("@" * 41, "")
    assert verdict.faults == (
        FailureCode.INVALID_ROW_EMPTY_ID,
        FailureCode.INVALID_ROW_BAD_CHARACTERS,
        FailureCode.INVALID_ROW_NAME_TOO_LONG,
    )
    assert verdict.code is verdict.faults[0]


def test_duplicate_fault_is_listed_last_with_other_faults() -> None:
    """TT-AC3-E13: a duplicate row with a bad name lists both faults."""
    _, second = validate_rows([RowInput(2, "Asha", "A1"), RowInput(3, "B@d", "A1")], RULES)
    assert second.faults == (
        FailureCode.INVALID_ROW_BAD_CHARACTERS,
        FailureCode.DUPLICATE_ID,
    )


# ---- edge -----------------------------------------------------------------------------


def test_exactly_40_latin_characters_valid_and_41_invalid() -> None:
    """TT-AC3-E1."""
    assert check(n.LATIN_40).valid
    assert not check(n.LATIN_41).valid


def test_grapheme_counting_not_code_point_counting_for_devanagari() -> None:
    """TT-AC3-E2 (A1): 40 graphemes of two code points each is valid."""
    assert len(n.DEVANAGARI_40_GRAPHEMES) == 80
    assert count_graphemes(n.DEVANAGARI_40_GRAPHEMES) == 40
    assert check(n.DEVANAGARI_40_GRAPHEMES).valid
    assert check(n.DEVANAGARI_41_GRAPHEMES).code is FailureCode.INVALID_ROW_NAME_TOO_LONG


def test_count_graphemes_basics() -> None:
    """TT-AC3-E2."""
    assert count_graphemes("") == 0
    assert count_graphemes("abc") == 3
    assert count_graphemes(n.KI) == 1


def test_limit_follows_the_rules_argument_not_a_constant() -> None:
    """TT-AC3-E3."""
    rules = RowRules(max_name_graphemes=10)
    assert check("A" * 10, rules=rules).valid
    assert check("A" * 11, rules=rules).code is FailureCode.INVALID_ROW_NAME_TOO_LONG


def test_surrounding_whitespace_is_trimmed_before_checks() -> None:
    """TT-AC3-E4."""
    assert check("  " + n.LATIN_40 + "  ").valid
    assert check("Raj   Kumar").valid  # inner multiple spaces are allowed


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("RJ/12/097", "rj_12_097"),
        ("RJ12", " rj12 "),
        ("\u00c4B", "\u00e4b"),
        (n.SLASHED_ID, n.SLASHED_ID.lower()),
        ("A/1", "A_1"),
        ("abc", "ABC"),
        ("\u0906\u0930/12", "\u0906\u0930_12"),
    ],
)
def test_duplicate_ids_use_trim_casefold_sanitise_comparison(first: str, second: str) -> None:
    """TT-AC3-E5, E12, AC11-E5, AC11-N5 (A2)."""
    _, later = validate_rows([RowInput(2, "Asha", first), RowInput(3, "Bina", second)], RULES)
    assert later.code is FailureCode.DUPLICATE_ID


def test_ids_that_differ_by_leading_zero_are_not_duplicates() -> None:
    """TT-AC3-E5."""
    verdicts = list(validate_rows([RowInput(2, "A", "RJ12"), RowInput(3, "B", "RJ012")], RULES))
    assert all(v.valid for v in verdicts)


def test_id_with_slashes_is_a_valid_id() -> None:
    """TT-AC3-E6."""
    assert check("Asha", n.SLASHED_ID).valid


def test_ten_thousand_character_name_is_rejected_quickly() -> None:
    """TT-AC3-E8: no catastrophic backtracking."""
    started = time.perf_counter()
    verdict = check("a" * 10_000)
    assert verdict.code is FailureCode.INVALID_ROW_NAME_TOO_LONG
    assert time.perf_counter() - started < 1.0


def test_same_id_three_times_names_row_one_for_rows_two_and_three() -> None:
    """TT-AC3-E9."""
    rows = [RowInput(2, "A", "X"), RowInput(3, "B", "X"), RowInput(4, "C", "X")]
    verdicts = list(validate_rows(rows, RULES))
    assert [v.duplicate_of for v in verdicts] == [None, 2, 2]


def test_invalid_spoken_name_uses_same_code_family() -> None:
    """TT-AC3-E10."""
    assert check("Asha", spoken="B@d").code is FailureCode.INVALID_ROW_BAD_CHARACTERS
    assert check("Asha", spoken="A" * 41).code is FailureCode.INVALID_ROW_NAME_TOO_LONG


def test_empty_spoken_name_falls_back_to_the_name() -> None:
    """TT-AC3-E10."""
    assert effective_spoken_name("Asha", None) == "Asha"
    assert effective_spoken_name(" Asha ", "  ") == "Asha"
    assert effective_spoken_name("Asha", " Aasha ") == "Aasha"
    assert check("Asha", spoken="  ").valid


def test_validate_rows_is_lazy_and_streams() -> None:
    """TT-AC4-E4 (domain side): works on a generator and yields incrementally."""
    consumed: list[int] = []

    def source() -> Iterator[RowInput]:
        for i in range(2, 1000):
            consumed.append(i)
            yield RowInput(i, "Asha", f"ID{i}")

    iterator = iter(validate_rows(source(), RULES))
    next(iterator)
    assert len(consumed) < 5


def test_duplicate_detection_scales_linearly() -> None:
    """TT-AC4-E3: 20,000 rows of the same ID validate fast (O(n))."""
    rows = [RowInput(i, "Asha", "SAME") for i in range(2, 20_002)]
    started = time.perf_counter()
    verdicts = list(validate_rows(rows, RULES))
    assert time.perf_counter() - started < 3.0
    assert sum(v.valid for v in verdicts) == 1
