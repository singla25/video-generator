"""manifest.csv content (R6.4, A7): one line per input row, personal data, safe cells."""

from __future__ import annotations

import csv
import io

import pytest

from vidgen.services.manifest import MANIFEST_COLUMNS, ManifestRow, build_manifest_csv


def parse(text: str) -> list[list[str]]:
    """Parse CSV text."""
    return list(csv.reader(io.StringIO(text)))


def row(number: int, **kwargs: object) -> ManifestRow:
    """A manifest row with defaults for a completed render."""
    values: dict[str, object] = {
        "row_number": number,
        "name": "Asha",
        "voter_id": f"A{number}",
        "status": "COMPLETED",
        "file_name": f"A{number}.mp4",
        "failure_code": None,
        "message": None,
        "render_seconds": 2.5,
    }
    values.update(kwargs)
    return ManifestRow(**values)  # type: ignore[arg-type]


def test_columns_follow_a7() -> None:
    """A7: row number, name, ID, status, file name, failure code + message, render time."""
    assert MANIFEST_COLUMNS == (
        "row_number",
        "name",
        "voter_id",
        "status",
        "file_name",
        "failure_code",
        "message",
        "render_seconds",
    )


def test_one_line_per_input_row_in_sheet_order_plus_a_header() -> None:
    """TT-AC11-P6."""
    text = build_manifest_csv([row(3), row(2), row(4)])
    lines = parse(text)
    assert lines[0] == list(MANIFEST_COLUMNS)
    assert [line[0] for line in lines[1:]] == ["2", "3", "4"]


def test_failed_skipped_and_cancelled_rows_are_listed_too() -> None:
    """TT-AC11-P6: skipped rows are rows too."""
    rows = [
        row(2),
        row(3, status="FAILED", file_name=None, failure_code="TTS_FAILED", message="no voice"),
        row(4, status="SKIPPED", file_name=None, failure_code="DUPLICATE_ID", render_seconds=None),
        row(5, status="CANCELLED", file_name=None, render_seconds=None),
    ]
    lines = parse(build_manifest_csv(rows))[1:]
    assert [line[3] for line in lines] == ["COMPLETED", "FAILED", "SKIPPED", "CANCELLED"]
    assert lines[1][4:7] == ["", "TTS_FAILED", "no voice"]
    assert lines[2][7] == ""


def test_status_counts_add_up_to_the_number_of_input_rows() -> None:
    """TT-AC11-P7."""
    rows = [row(2), row(3, status="FAILED"), row(4, status="SKIPPED"), row(5, status="CANCELLED")]
    lines = parse(build_manifest_csv(rows))[1:]
    assert len(lines) == len(rows)


def test_name_and_id_are_included_as_written() -> None:
    """A7: the manifest is personal data and says so."""
    devanagari = "\u0930\u093e\u091c\u0947\u0936"
    lines = parse(build_manifest_csv([row(2, name=devanagari, voter_id="RJ/12/097")]))
    assert lines[1][1:3] == [devanagari, "RJ/12/097"]


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2+3", "@SUM(A1)"])
def test_formula_like_cells_are_neutralised(value: str) -> None:
    """TT-AC11-E10."""
    lines = parse(build_manifest_csv([row(2, name=value, voter_id=value)]))
    assert lines[1][1] == "'" + value
    assert lines[1][2] == "'" + value


def test_commas_quotes_and_newlines_survive_a_round_trip() -> None:
    """TT-AC11-E10."""
    name = 'Smith, "Jr."\nSecond line'
    lines = parse(build_manifest_csv([row(2, name=name)]))
    assert lines[1][1] == name


def test_empty_batch_gives_only_the_header() -> None:
    """TT-AC11-E6."""
    assert parse(build_manifest_csv([])) == [list(MANIFEST_COLUMNS)]


def test_render_time_is_written_as_a_plain_number() -> None:
    """A7."""
    assert parse(build_manifest_csv([row(2, render_seconds=2.5)]))[1][7] == "2.5"
