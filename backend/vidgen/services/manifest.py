"""manifest.csv content (R6.4, A7): one line per input row; personal data, safe cells."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass

from vidgen.domain.naming import output_file_name
from vidgen.ports.batches import RowView
from vidgen.services.batch_queries import failure_message
from vidgen.services.batch_rules import neutralise_cell

MANIFEST_COLUMNS = (
    "row_number",
    "name",
    "voter_id",
    "status",
    "file_name",
    "failure_code",
    "message",
    "render_seconds",
)
COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class ManifestRow:
    """One line of the manifest."""

    row_number: int
    name: str
    voter_id: str
    status: str
    file_name: str | None
    failure_code: str | None
    message: str | None
    render_seconds: float | None


def manifest_row(row: RowView) -> ManifestRow:
    """The manifest line for a stored row."""
    done = row.status == COMPLETED and row.output_key is not None
    return ManifestRow(
        row_number=row.row_number,
        name=row.name,
        voter_id=row.voter_id,
        status=row.status,
        file_name=output_file_name(row.voter_id) if done else None,
        failure_code=row.failure_code,
        message=failure_message(row.failure_code) if row.failure_code else None,
        render_seconds=row.render_seconds,
    )


def build_manifest_csv(rows: Iterable[ManifestRow]) -> str:
    """CSV text with a header and one line per row in sheet order; formulas are neutralised."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MANIFEST_COLUMNS)
    for row in sorted(rows, key=lambda r: r.row_number):
        writer.writerow(
            [
                row.row_number,
                neutralise_cell(row.name),
                neutralise_cell(row.voter_id),
                row.status,
                row.file_name or "",
                row.failure_code or "",
                row.message or "",
                "" if row.render_seconds is None else row.render_seconds,
            ]
        )
    return buffer.getvalue()
