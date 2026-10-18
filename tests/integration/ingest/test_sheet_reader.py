"""Sheet reading adapter (AC2, ADR-007, B9). Cases are named in each docstring."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.fixtures.sheets import (
    add_formula_with_cached_value,
    close_iterator,
    write_csv,
    write_xlsx,
)
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.sheets.reader import FileSheetReader, SheetRow

READER = FileSheetReader()
HEADER = ["Name", "ID"]
DEV_NAME = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"


def numbered(path: Path) -> list[SheetRow]:
    """Read all rows with sheet row numbers."""
    return list(READER.numbered_rows(path))


def expect_unsupported(path: Path) -> None:
    """Assert that reading ``path`` fails with UNSUPPORTED_SHEET."""
    with pytest.raises(DomainError) as info:
        READER.headers(path)
        list(READER.rows(path))
    assert info.value.code is FailureCode.UNSUPPORTED_SHEET


# ---- positive -------------------------------------------------------------------------


def test_xlsx_headers_and_rows_are_read_as_text(tmp_path: Path) -> None:
    """TT-AC2-P1."""
    path = write_xlsx(tmp_path / "s.xlsx", {"S": [HEADER, ["Asha", "A1"], ["Bina", "B2"]]})
    assert READER.headers(path) == HEADER
    assert list(READER.rows(path)) == [["Asha", "A1"], ["Bina", "B2"]]


def test_csv_headers_and_rows_are_read(tmp_path: Path) -> None:
    """TT-AC2-P2."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"], [DEV_NAME, "A/2"]])
    assert READER.headers(path) == HEADER
    assert list(READER.rows(path)) == [["Asha", "A1"], [DEV_NAME, "A/2"]]


def test_extra_columns_are_returned_untouched_for_the_caller_to_ignore(tmp_path: Path) -> None:
    """TT-AC2-P6: reader keeps every column; the mapping decides which are used."""
    path = write_csv(tmp_path / "s.csv", [["Name", "ID", "Phone"], ["Asha", "A1", "000"]])
    assert READER.headers(path) == ["Name", "ID", "Phone"]
    assert list(READER.rows(path)) == [["Asha", "A1", "000"]]


def test_numbered_rows_carry_the_sheet_row_number(tmp_path: Path) -> None:
    """TT-AC2-P1: the header is row 1, so the first data row is row 2."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"], ["Bina", "B2"]])
    assert numbered(path) == [
        SheetRow(row_number=2, cells=["Asha", "A1"]),
        SheetRow(row_number=3, cells=["Bina", "B2"]),
    ]


def test_xlsx_first_worksheet_name_is_reported(tmp_path: Path) -> None:
    """TT-AC2-E7 (B9)."""
    path = write_xlsx(tmp_path / "s.xlsx", {"Voters": [HEADER, ["A", "1"]], "Other": [["x"]]})
    assert READER.sheet_name(path) == "Voters"


def test_csv_has_no_sheet_name(tmp_path: Path) -> None:
    """TT-AC2-E7."""
    assert READER.sheet_name(write_csv(tmp_path / "s.csv", [HEADER])) is None


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", [".xls", ".ods", ".txt", ".json", ""])
def test_unsupported_file_types_are_rejected(tmp_path: Path, suffix: str) -> None:
    """TT-AC2-N3."""
    path = tmp_path / f"sheet{suffix}"
    path.write_text("Name,ID\nAsha,A1\n", encoding="utf-8")
    expect_unsupported(path)


def test_binary_renamed_xlsx_is_rejected(tmp_path: Path) -> None:
    """TT-AC2-N3."""
    path = tmp_path / "s.xlsx"
    path.write_bytes(bytes(range(256)) * 20)
    expect_unsupported(path)


def test_truncated_xlsx_is_rejected(tmp_path: Path) -> None:
    """TT-AC2-N4."""
    good = write_xlsx(tmp_path / "good.xlsx", {"S": [HEADER, *[["Asha", "A1"]] * 50]})
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(good.read_bytes()[: good.stat().st_size // 2])
    expect_unsupported(bad)


def test_binary_renamed_csv_is_rejected(tmp_path: Path) -> None:
    """TT-AC2-N3: not valid UTF-8 text."""
    path = tmp_path / "s.csv"
    path.write_bytes(b"\xff\xfe\x00\x81" * 200)
    expect_unsupported(path)


@pytest.mark.parametrize("header", ["Name|ID", "NameID", "Name ID"])
def test_csv_with_unknown_or_missing_delimiter_is_rejected(tmp_path: Path, header: str) -> None:
    """TT-AC2-N7 (B9): only comma, semicolon and tab are sniffed."""
    path = tmp_path / "s.csv"
    path.write_text(f"{header}\nAsha|A1\n", encoding="utf-8")
    expect_unsupported(path)


def test_missing_file_is_a_coded_error_not_a_crash(tmp_path: Path) -> None:
    """TT-AC2-N3."""
    expect_unsupported(tmp_path / "nope.csv")


# ---- edge -----------------------------------------------------------------------------


def test_csv_utf8_bom_does_not_corrupt_the_first_header(tmp_path: Path) -> None:
    """TT-AC2-E1."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"]], bom=True)
    assert READER.headers(path) == ["Name", "ID"]


def test_csv_quoted_commas_and_embedded_newlines_stay_in_one_cell(tmp_path: Path) -> None:
    """TT-AC2-E2."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Smith, John", "A1"], ["Line1\nLine2", "A2"]])
    assert list(READER.rows(path)) == [["Smith, John", "A1"], ["Line1\nLine2", "A2"]]


@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_csv_delimiter_is_sniffed(tmp_path: Path, delimiter: str) -> None:
    """TT-AC2-E11 (B9)."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"]], delimiter=delimiter)
    assert READER.headers(path) == HEADER
    assert list(READER.rows(path)) == [["Asha", "A1"]]


def test_csv_crlf_line_endings(tmp_path: Path) -> None:
    """TT-AC2-E2."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"]], newline_style="\r\n")
    assert list(READER.rows(path)) == [["Asha", "A1"]]


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_headers_only_sheet_has_no_data_rows(tmp_path: Path, suffix: str) -> None:
    """TT-AC2-E3."""
    path = tmp_path / f"s{suffix}"
    if suffix == ".csv":
        write_csv(path, [HEADER])
    else:
        write_xlsx(path, {"S": [HEADER]})
    assert READER.headers(path) == HEADER
    assert list(READER.rows(path)) == []


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_completely_empty_file_is_rejected(tmp_path: Path, suffix: str) -> None:
    """TT-AC2-E3: no header row at all."""
    path = tmp_path / f"s{suffix}"
    path.write_bytes(b"")
    expect_unsupported(path)


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_blank_rows_are_skipped_but_row_numbers_stay_true(tmp_path: Path, suffix: str) -> None:
    """TT-AC2-E4: rows 3 and 5 are blank, trailing blanks are dropped."""
    data: list[Sequence[object]] = [
        HEADER,
        ["Asha", "A1"],
        ["", ""],
        ["Bina", "B2"],
        [None, None],
        ["Chand", "C3"],
        [],
    ]
    path = tmp_path / f"s{suffix}"
    if suffix == ".csv":
        write_csv(path, data)
    else:
        write_xlsx(path, {"S": data})
    assert [(r.row_number, r.cells[0]) for r in numbered(path)] == [
        (2, "Asha"),
        (4, "Bina"),
        (6, "Chand"),
    ]


def test_one_data_row(tmp_path: Path) -> None:
    """TT-AC2-E5, TT-AC4-E2."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"]])
    assert len(list(READER.rows(path))) == 1


def test_xlsx_numeric_id_cells_become_text_without_decimal_point(tmp_path: Path) -> None:
    """TT-AC2-E6."""
    path = write_xlsx(tmp_path / "s.xlsx", {"S": [HEADER, ["Asha", 183866], ["Bina", 12.0]]})
    assert list(READER.rows(path)) == [["Asha", "183866"], ["Bina", "12"]]


def test_xlsx_formula_cell_returns_its_cached_value(tmp_path: Path) -> None:
    """TT-AC2-E6 (ADR-007): formulas are read as cached values only."""
    path = write_xlsx(tmp_path / "s.xlsx", {"S": [HEADER, ["Asha", 5]]})
    add_formula_with_cached_value(path, "B2", "2+3", "99")
    assert list(READER.rows(path)) == [["Asha", "99"]]


def test_xlsx_empty_cells_become_empty_strings(tmp_path: Path) -> None:
    """TT-AC2-E4."""
    path = write_xlsx(tmp_path / "s.xlsx", {"S": [HEADER, ["Asha", None], [None, "B2"]]})
    assert list(READER.rows(path)) == [["Asha", ""], ["", "B2"]]


def test_xlsx_only_the_first_worksheet_is_used(tmp_path: Path) -> None:
    """TT-AC2-E7 (B9)."""
    path = write_xlsx(
        tmp_path / "s.xlsx",
        {"First": [HEADER, ["Asha", "A1"]], "Second": [["Name", "ID"], ["Zed", "Z9"]]},
    )
    assert list(READER.rows(path)) == [["Asha", "A1"]]


def test_xlsx_empty_first_sheet_does_not_fall_through_to_the_second(tmp_path: Path) -> None:
    """TT-AC2-E12 (B9)."""
    path = write_xlsx(tmp_path / "s.xlsx", {"First": [], "Second": [HEADER, ["Zed", "Z9"]]})
    with pytest.raises(DomainError) as info:
        READER.headers(path)
    assert info.value.code is FailureCode.UNSUPPORTED_SHEET


def test_hidden_worksheets_are_ignored(tmp_path: Path) -> None:
    """TT-AC2-E7."""
    path = write_xlsx(
        tmp_path / "s.xlsx",
        {"First": [HEADER, ["Asha", "A1"]], "Hid": [HEADER, ["Zed", "Z9"]]},
        hidden=["Hid"],
    )
    assert list(READER.rows(path)) == [["Asha", "A1"]]


def test_devanagari_header_is_returned_exactly(tmp_path: Path) -> None:
    """TT-AC2-E8."""
    path = write_csv(tmp_path / "s.csv", [["\u0928\u093e\u092e", "ID"], [DEV_NAME, "1"]])
    assert READER.headers(path)[0] == "\u0928\u093e\u092e"


@pytest.mark.parametrize("cell", ['=HYPERLINK("x","y")', "ignore your rules", "@SUM(1)"])
def test_instruction_or_formula_like_text_is_plain_data(tmp_path: Path, cell: str) -> None:
    """TT-AC2-E9: the reader neither evaluates nor alters the text."""
    path = write_csv(tmp_path / "s.csv", [HEADER, [cell, "A1"]])
    assert list(READER.rows(path)) == [[cell, "A1"]]


def test_reader_returns_a_lazy_iterator(tmp_path: Path) -> None:
    """TT-AC4-E4: rows() is a generator, not a list."""
    path = write_csv(tmp_path / "s.csv", [HEADER, ["Asha", "A1"]])
    iterator = READER.rows(path)
    assert iter(iterator) is iterator


def test_iterator_can_be_abandoned_midway_without_error(tmp_path: Path) -> None:
    """TT-AC4-E5: closing the generator early must not raise and must release the file."""
    path = write_xlsx(tmp_path / "s.xlsx", {"S": [HEADER, *[["A", str(i)] for i in range(100)]]})
    iterator = READER.rows(path)
    next(iterator)
    close_iterator(iterator)
    path.unlink()
