"""Synthetic spreadsheet builders (csv and xlsx). Code only; all names are invented."""

from __future__ import annotations

import csv
import re
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from openpyxl import Workbook


def write_csv(
    path: Path,
    rows: Iterable[Sequence[object]],
    *,
    delimiter: str = ",",
    bom: bool = False,
    newline_style: str = "\n",
) -> Path:
    """Write ``rows`` as CSV (UTF-8, optional BOM) using the stdlib writer."""
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator=newline_style)
        writer.writerows(rows)
    return path


def write_xlsx(
    path: Path,
    sheets: dict[str, Iterable[Sequence[object]]],
    *,
    hidden: Sequence[str] = (),
) -> Path:
    """Write a workbook with one worksheet per entry (first entry = first worksheet)."""
    workbook = Workbook(write_only=True)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(list(row))
        if title in hidden:
            sheet.sheet_state = "hidden"
    workbook.save(path)
    return path


def add_formula_with_cached_value(path: Path, cell: str, formula: str, cached: str) -> Path:
    """Patch the first worksheet so ``cell`` holds a formula with a cached result.

    openpyxl cannot write cached formula results, so the sheet XML is rewritten.
    """
    temp = path.with_suffix(".patched")
    pattern = re.compile(rf'<c r="{cell}"[^>]*?>.*?</c>', re.DOTALL)
    replacement = f'<c r="{cell}"><f>{formula}</f><v>{cached}</v></c>'
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = pattern.sub(replacement, data.decode("utf-8"), count=1)
                data = text.encode("utf-8")
            out.writestr(item, data)
    temp.replace(path)
    return path


def close_iterator(iterator: Iterator[object]) -> None:
    """Close a generator-backed iterator early (no-op if it has no ``close``)."""
    close = getattr(iterator, "close", None)
    if callable(close):
        close()
