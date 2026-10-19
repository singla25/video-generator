"""Helpers for the batch API tests: sheets, requests and direct database edits.

Worker behaviour (rendering rows) belongs to T13/T14. These tests simulate its results by
editing rows in the database and by calling the documented service hooks.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from httpx import Response
from openpyxl import Workbook
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from tests.fixtures.doubles import pdf_bytes
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import (
    confirm_slot,
    new_template,
    set_slot,
    upload_consent,
)
from vidgen.infrastructure.db.models import Batch, BatchRow

HEADER = ["Name", "ID"]
Rows = Sequence[Sequence[object]]


def people(count: int, *, prefix: str = "ID") -> list[list[str]]:
    """``count`` valid fake rows with unique IDs."""
    return [[f"Person {chr(65 + i % 26)}", f"{prefix}{i + 1}"] for i in range(count)]


def csv_bytes(rows: Rows, *, delimiter: str = ",", bom: bool = False) -> bytes:
    """Rows as CSV bytes (header must be part of ``rows``)."""
    buffer = io.StringIO(newline="")
    csv.writer(buffer, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return buffer.getvalue().encode("utf-8-sig" if bom else "utf-8")


def xlsx_bytes(sheets: dict[str, Rows]) -> bytes:
    """A workbook with one worksheet per entry (first entry is the first sheet)."""
    workbook = Workbook(write_only=True)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def usable_template(env: Env, **kwargs: Any) -> str:
    """A template with consent and a confirmed slot (1.0-1.6 s)."""
    template_id = new_template(env, **kwargs)
    assert upload_consent(env, template_id, content=pdf_bytes()).status_code == 200
    assert set_slot(env, template_id, 1.0, 1.6).status_code == 200
    assert confirm_slot(env, template_id).status_code == 200
    return template_id


def create_batch(
    env: Env,
    template_id: str,
    rows: Rows | None = None,
    *,
    content: bytes | None = None,
    filename: str = "sheet.csv",
    name_column: str | None = "Name",
    id_column: str | None = "ID",
    spoken_column: str | None = None,
    header: Sequence[str] = HEADER,
) -> Response:
    """POST /batches (multipart). ``rows`` excludes the header; pass ``content`` to override."""
    body = content if content is not None else csv_bytes([list(header), *(rows or people(3))])
    data: dict[str, str] = {"template_id": template_id}
    if name_column is not None:
        data["name_column"] = name_column
    if id_column is not None:
        data["id_column"] = id_column
    if spoken_column is not None:
        data["spoken_name_column"] = spoken_column
    return env.client.post(
        "/batches",
        files={"sheet": (filename, body, "application/octet-stream")},
        data=data,
        headers=env.csrf,
    )


def new_batch(env: Env, rows: Rows | None = None, **kwargs: Any) -> str:
    """Create a usable template and a batch; return the batch id."""
    template_id = kwargs.pop("template_id", None) or usable_template(env)
    response = create_batch(env, template_id, rows, **kwargs)
    assert response.status_code == 201, response.text
    batch_id: str = response.json()["id"]
    return batch_id


def get_batch(env: Env, batch_id: str) -> dict[str, Any]:
    """GET /batches/{id}."""
    response = env.client.get(f"/batches/{batch_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def status_of(env: Env, batch_id: str) -> dict[str, Any]:
    """GET /batches/{id}/status."""
    response = env.client.get(f"/batches/{batch_id}/status")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def counts_of(env: Env, batch_id: str) -> dict[str, int]:
    """The overview counts of a batch."""
    counts: dict[str, int] = status_of(env, batch_id)["counts"]
    return counts


def post_action(env: Env, batch_id: str, action: str) -> Response:
    """POST /batches/{id}/{action} (preview, preview/approve, pause, resume, cancel, ...)."""
    return env.client.post(f"/batches/{batch_id}/{action}", headers=env.csrf)


def start(
    env: Env, batch_id: str, *, key: str | None = "key-1", folder: str | None = None
) -> Response:
    """POST /batches/{id}/start with an Idempotency-Key and an optional folder name."""
    headers = dict(env.csrf)
    if key is not None:
        headers["Idempotency-Key"] = key
    body: dict[str, Any] = {} if folder is None else {"folder_name": folder}
    return env.client.post(f"/batches/{batch_id}/start", json=body, headers=headers)


def approve_preview(env: Env, batch_id: str) -> None:
    """Request a preview, let the 'worker' finish it, and approve it."""
    assert post_action(env, batch_id, "preview").status_code == 202
    key = env.storage.write(f"previews/{batch_id}.mp4", io.BytesIO(b"PREVIEW-BYTES"))
    env.app.state.container.batches.preview_rendered(UUID(batch_id), key)
    assert post_action(env, batch_id, "preview/approve").status_code == 200


def running_batch(env: Env, rows: Rows | None = None, **kwargs: Any) -> str:
    """A batch that is approved and started; returns its id."""
    batch_id = new_batch(env, rows, **kwargs)
    approve_preview(env, batch_id)
    assert start(env, batch_id).status_code == 200
    return batch_id


# ---- direct database edits (stand-ins for the worker) ---------------------------------


def row_ids(db: Engine, batch_id: str) -> dict[int, UUID]:
    """Row id by sheet row number."""
    with Session(db) as session:
        rows = session.execute(
            select(BatchRow.row_number, BatchRow.id).where(BatchRow.batch_id == UUID(batch_id))
        )
        return {number: row_id for number, row_id in rows}


def row_status(db: Engine, batch_id: str) -> dict[int, str]:
    """Status by sheet row number."""
    with Session(db) as session:
        rows = session.execute(
            select(BatchRow.row_number, BatchRow.status).where(BatchRow.batch_id == UUID(batch_id))
        )
        return {number: status for number, status in rows}


def set_rows(db: Engine, batch_id: str, numbers: Sequence[int], **values: Any) -> None:
    """Update columns of the given rows."""
    with Session(db) as session:
        session.execute(
            update(BatchRow)
            .where(BatchRow.batch_id == UUID(batch_id), BatchRow.row_number.in_(numbers))
            .values(**values)
        )
        session.commit()


def finish_row(
    db: Engine,
    batch_id: str,
    number: int,
    *,
    seconds: float = 2.0,
    at: datetime,
    output_key: str | None = None,
) -> None:
    """Mark a row COMPLETED the way the worker would."""
    set_rows(
        db,
        batch_id,
        [number],
        status="COMPLETED",
        render_seconds=seconds,
        finished_at=at,
        output_key=output_key,
    )


def set_batch(db: Engine, batch_id: str, **values: Any) -> None:
    """Update columns of a batch."""
    with Session(db) as session:
        session.execute(update(Batch).where(Batch.id == UUID(batch_id)).values(**values))
        session.commit()


def table_count(db: Engine, model: Any) -> int:
    """Number of rows in a table."""
    with Session(db) as session:
        return session.query(model).count()
