"""Streaming reader for .xlsx and .csv uploads (AC2, ADR-007, B9).

Nothing is held in memory beyond the current row. Every file problem becomes a coded
``UNSUPPORTED_SHEET`` error whose message never contains cell contents.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from collections.abc import Callable, Generator
from contextlib import closing
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.ports.models import SheetRow

CSV_SUFFIX = ".csv"
XLSX_SUFFIX = ".xlsx"
CSV_ENCODING = "utf-8-sig"  # strips a leading BOM so the first header stays clean
CSV_DELIMITERS = (",", ";", "\t")
HEADER_ROW_NUMBER = 1
_VISIBLE = "visible"
_XLSX_ERRORS = (BadZipFile, KeyError, InvalidFileException, ET.ParseError, EOFError, ValueError)


def _unsupported() -> DomainError:
    """The single error used for every unreadable sheet."""
    return DomainError(FailureCode.UNSUPPORTED_SHEET)


def _cell_text(value: object) -> str:
    """Render a cell as text; whole numbers lose the '.0' that Excel adds."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sniff_delimiter(header_line: str) -> str:
    """Pick the most frequent of , ; tab in the header line, or fail (B9)."""
    best = max(CSV_DELIMITERS, key=header_line.count)
    if header_line.count(best) == 0:
        raise _unsupported()
    return best


def _stream_csv(path: Path) -> Generator[list[str], None, None]:
    """Yield every CSV record, header first."""
    try:
        with path.open(encoding=CSV_ENCODING, newline="") as handle:
            delimiter = _sniff_delimiter(handle.readline())
            handle.seek(0)
            yield from csv.reader(handle, delimiter=delimiter)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise _unsupported() from exc


def _stream_xlsx(path: Path) -> Generator[list[str], None, None]:
    """Yield every row of the first visible worksheet, header first."""
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (OSError, *_XLSX_ERRORS) as exc:
        raise _unsupported() from exc
    try:
        sheet = _first_visible_sheet(workbook)
        width = 0
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            cells = [_cell_text(cell) for cell in row]
            width = len(cells) if index == 0 else width
            # Read-only mode drops trailing empty cells; pad back to the header width.
            yield cells + [""] * (width - len(cells))
    except _XLSX_ERRORS as exc:
        raise _unsupported() from exc
    finally:
        workbook.close()


def _first_visible_sheet(workbook: Any) -> Any:
    """Return the first non-hidden worksheet; later sheets are never read (B9)."""
    for sheet in workbook.worksheets:
        if sheet.sheet_state == _VISIBLE:
            return sheet
    raise _unsupported()


def _streamer(path: Path) -> Callable[[Path], Generator[list[str], None, None]]:
    """Choose the row streamer from the file extension (content errors surface while reading)."""
    suffix = path.suffix.lower()
    if suffix == CSV_SUFFIX:
        return _stream_csv
    if suffix == XLSX_SUFFIX:
        return _stream_xlsx
    raise _unsupported()


class FileSheetReader:
    """Reads the first worksheet of an .xlsx file or a delimiter-sniffed .csv file."""

    def headers(self, path: Path) -> list[str]:
        """Return the header cells; fail if the sheet has no rows."""
        with closing(_streamer(path)(path)) as rows:
            first = next(rows, None)
        if first is None:
            raise _unsupported()
        return first

    def numbered_rows(self, path: Path) -> Generator[SheetRow, None, None]:
        """Yield non-blank data rows with true sheet row numbers (header = row 1)."""
        with closing(_streamer(path)(path)) as rows:
            for number, cells in enumerate(rows, start=HEADER_ROW_NUMBER):
                is_data = number > HEADER_ROW_NUMBER
                if is_data and any(cell.strip() for cell in cells):
                    yield SheetRow(number, cells)

    def rows(self, path: Path) -> Generator[list[str], None, None]:
        """Yield non-blank data rows as lists of text cells."""
        with closing(self.numbered_rows(path)) as numbered:
            for row in numbered:
                yield row.cells

    def sheet_name(self, path: Path) -> str | None:
        """Name of the worksheet used (xlsx) or None (csv)."""
        if path.suffix.lower() != XLSX_SUFFIX:
            return None
        try:
            workbook = load_workbook(path, read_only=True)
        except (OSError, *_XLSX_ERRORS) as exc:
            raise _unsupported() from exc
        with closing(workbook):
            return str(_first_visible_sheet(workbook).title)
