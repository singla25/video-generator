"""Output folder naming (AC11, B4). Cases TT-AC11-P1..P3, N1..N3, E1, E3, E6, E7, E12, E13."""

from __future__ import annotations

from datetime import date

import pytest

from vidgen.domain.codes import FailureCode
from vidgen.domain.naming import (
    InvalidFolderNameError,
    default_folder_name,
    resolve_folder_name,
    unique_folder_name,
)

DAY = date(2026, 10, 18)


def test_default_folder_name_is_date_dash_valid_row_count() -> None:
    """TT-AC11-P1."""
    assert default_folder_name(DAY, 7) == "2026-10-18-7"


def test_default_folder_name_depends_only_on_its_arguments() -> None:
    """TT-AC11-E7: the date is the batch-start date passed in, never 'today'."""
    assert default_folder_name(date(2026, 12, 31), 3) == "2026-12-31-3"
    assert default_folder_name(date(2027, 1, 1), 3) == "2027-01-01-3"


def test_default_folder_name_with_no_valid_rows_is_an_error() -> None:
    """TT-AC11-E6: a `...-0` folder is never produced."""
    with pytest.raises(ValueError, match="valid"):
        default_folder_name(DAY, 0)


def test_custom_folder_name_is_accepted() -> None:
    """TT-AC11-P2."""
    assert resolve_folder_name("Ward 12 Campaign", DAY, 5) == "Ward 12 Campaign"


@pytest.mark.parametrize(
    "custom",
    ["\u092a\u094d\u0930\u091a\u093e\u0930 2026", "\u062d\u0645\u0644\u0629", "Launch \U0001f680"],
)
def test_unicode_rtl_and_emoji_folder_names_are_allowed(custom: str) -> None:
    """TT-AC11-E3."""
    assert resolve_folder_name(custom, DAY, 5) == custom


def test_folder_name_is_nfc_normalised_and_trimmed() -> None:
    """TT-AC11-E3."""
    assert resolve_folder_name("  Cafe\u0301  ", DAY, 5) == "Caf\u00e9"


@pytest.mark.parametrize("custom", [None, "", "   ", "\t \n"])
def test_empty_custom_name_falls_back_to_default(custom: str | None) -> None:
    """TT-AC11-E12, E13 (B4)."""
    assert resolve_folder_name(custom, DAY, 7) == "2026-10-18-7"


@pytest.mark.parametrize(
    "custom",
    [
        "../../etc",
        "/abs/path",
        "..\\x",
        "a/../b",
        ".",
        "..",
        "a/b",
        "a\\b",
        "bad<name",
        "bad>name",
        "bad:name",
        'bad"name',
        "bad|name",
        "bad?name",
        "bad*name",
        "nul\x00byte",
        "ctl\x1fchar",
        "trailing.",
        "CON",
        "nul",
        "LPT1",
        "con.txt",
        "x" * 256,
    ],
)
def test_traversal_illegal_and_reserved_folder_names_are_rejected(custom: str) -> None:
    """TT-AC11-N1, N2: `INVALID_FOLDER_NAME`."""
    with pytest.raises(InvalidFolderNameError) as info:
        resolve_folder_name(custom, DAY, 7)
    assert info.value.code is FailureCode.INVALID_FOLDER_NAME


def test_unique_folder_name_returns_base_when_free() -> None:
    """TT-AC11-P3."""
    assert unique_folder_name("2026-10-18-7", set()) == "2026-10-18-7"


def test_unique_folder_name_adds_dash_two_then_dash_three() -> None:
    """TT-AC11-P3."""
    assert unique_folder_name("B", {"B"}) == "B-2"
    assert unique_folder_name("B", {"B", "B-2"}) == "B-3"


def test_unique_folder_name_has_no_off_by_one_after_many_suffixes() -> None:
    """TT-AC11-E1."""
    existing = {"B"} | {f"B-{i}" for i in range(2, 51)}
    assert unique_folder_name("B", existing) == "B-51"


def test_unique_folder_name_skips_gaps_to_first_free_suffix() -> None:
    """TT-AC11-E1."""
    assert unique_folder_name("B", {"B", "B-3"}) == "B-2"


def test_unique_folder_name_compares_case_insensitively() -> None:
    """TT-AC11-E5: case-insensitive file systems."""
    assert unique_folder_name("Batch", {"BATCH"}) == "Batch-2"
