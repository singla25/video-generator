"""Look into an uploaded sheet without creating anything (DD-16): headers, sample, row count."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.ports import SheetReader

SAMPLE_ROWS = 5
CSV_SHEET_NAME = "CSV"  # CSV files have no worksheet name


@dataclass(frozen=True)
class SheetInspection:
    """What the user needs to choose the columns."""

    sheet_name: str
    headers: list[str]
    sample_rows: list[list[str]] = field(default_factory=list)
    row_count: int = 0


def inspect_sheet(reader: SheetReader, path: Path) -> SheetInspection:
    """Read the sheet in a stream; an unreadable sheet or one without data rows is refused."""
    headers = [header.strip() for header in reader.headers(path)]
    sample: list[list[str]] = []
    count = 0
    for row in reader.rows(path):
        count += 1
        if count <= SAMPLE_ROWS:
            sample.append(row)
    if count == 0:
        raise DomainError(FailureCode.UNSUPPORTED_SHEET)
    return SheetInspection(reader.sheet_name(path) or CSV_SHEET_NAME, headers, sample, count)
