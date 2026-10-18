"""Sheet reading at scale (AC4). 1k-row timing and 100k-row streaming memory."""

from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

import pytest

from tests.fixtures.sheets import close_iterator, write_csv, write_xlsx
from vidgen.domain.validation import RowInput, RowRules, validate_rows
from vidgen.infrastructure.sheets.reader import FileSheetReader

READER = FileSheetReader()
MAX_BASELINE_GROWTH = 200 * 1024 * 1024  # A9: 200 MB above baseline
HEADER = ["Name", "ID"]


def generate(count: int) -> list[list[str]]:
    """Fake rows: valid name, unique ID."""
    return [HEADER, *[[f"Person {chr(65 + i % 26)}", f"ID{i}"] for i in range(count)]]


def validate_all(path: Path) -> int:
    """Read and validate every row; return the number of valid rows."""
    rows = (RowInput(r.row_number, r.cells[0], r.cells[1]) for r in READER.numbered_rows(path))
    return sum(v.valid for v in validate_rows(rows, RowRules()))


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_one_thousand_rows_read_and_validate_in_under_three_seconds(
    tmp_path: Path, suffix: str
) -> None:
    """TT-AC4-P1, P2."""
    path = tmp_path / f"s{suffix}"
    if suffix == ".csv":
        write_csv(path, generate(1000))
    else:
        write_xlsx(path, {"S": generate(1000)})
    started = time.perf_counter()
    valid = validate_all(path)
    elapsed = time.perf_counter() - started
    assert valid == 1000
    assert elapsed < 3.0


def test_thousand_rows_with_all_duplicate_ids_is_still_fast(tmp_path: Path) -> None:
    """TT-AC4-E3."""
    path = write_csv(tmp_path / "s.csv", [HEADER, *[["Asha", "SAME"]] * 1000])
    started = time.perf_counter()
    assert validate_all(path) == 1
    assert time.perf_counter() - started < 3.0


def test_zero_data_rows_reads_as_empty(tmp_path: Path) -> None:
    """TT-AC4-E1."""
    path = write_csv(tmp_path / "s.csv", [HEADER])
    assert list(READER.rows(path)) == []


def test_first_row_is_available_without_reading_the_whole_file(tmp_path: Path) -> None:
    """TT-AC4-E4: peak memory after the first row stays tiny for a 30,000-row file."""
    path = write_csv(tmp_path / "s.csv", generate(30_000))
    tracemalloc.start()
    try:
        iterator = READER.rows(path)
        next(iterator)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024


@pytest.mark.slow
@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_hundred_thousand_rows_stream_within_the_memory_bound(tmp_path: Path, suffix: str) -> None:
    """TT-AC4-P3, P4: peak allocation while streaming 100k rows stays under 200 MB."""
    path = tmp_path / f"big{suffix}"
    if suffix == ".csv":
        write_csv(path, generate(100_000))
    else:
        write_xlsx(path, {"S": generate(100_000)})
    tracemalloc.start()
    try:
        count = sum(1 for _ in READER.rows(path))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert count == 100_000
    assert peak < MAX_BASELINE_GROWTH


@pytest.mark.slow
def test_memory_does_not_grow_with_row_count(tmp_path: Path) -> None:
    """TT-AC4-P3: streaming 10x the rows must not use 10x the memory."""
    peaks = []
    for count in (10_000, 100_000):
        path = write_csv(tmp_path / f"s{count}.csv", generate(count))
        tracemalloc.start()
        try:
            for _ in READER.rows(path):
                pass
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        peaks.append(peak)
    assert peaks[1] < peaks[0] * 3 + 1024 * 1024


def test_reading_never_writes_files_next_to_the_upload(tmp_path: Path) -> None:
    """TT-AC4-E5."""
    path = write_csv(tmp_path / "s.csv", generate(10))
    before = {p.name for p in tmp_path.iterdir()}
    iterator = READER.rows(path)
    next(iterator)
    close_iterator(iterator)
    assert {p.name for p in tmp_path.iterdir()} == before
