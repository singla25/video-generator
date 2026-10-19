"""Downloads: single video, streamed ZIP with manifest, failures CSV (AC15, A7, B5)."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.naming import output_file_name
from vidgen.ports import Storage
from vidgen.ports.batches import RowView
from vidgen.services.batch_queries import BatchQueries, failure_message
from vidgen.services.batch_rules import neutralise_cell
from vidgen.services.batch_support import BatchContext, load_batch
from vidgen.services.errors import BatchNotFoundError, StateConflictError

ZIP_CHUNK_BYTES = 1024 * 1024
MANIFEST_NAME = "manifest.csv"
FAILURE_HEADER = ["row_number", "name", "voter_id", "status", "failure_code", "message"]
MANIFEST_HEADER = [
    "row_number", "name", "voter_id", "status", "file_name", "failure_code", "message",
    "render_seconds",
]  # fmt: skip
FAILED_STATUSES = ["FAILED", "SKIPPED"]


@dataclass(frozen=True)
class ZipPlan:
    """What goes into the archive: (entry name, storage key) pairs plus the manifest text."""

    entries: list[tuple[str, str]]
    manifest: str


def _csv_text(rows: list[list[str]]) -> str:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def _message(row: RowView) -> str:
    return failure_message(row.failure_code) if row.failure_code else ""


class _Sink(io.RawIOBase):
    """Write-only buffer the ZIP writer fills; the generator drains it chunk by chunk."""

    def __init__(self) -> None:
        self._chunks: deque[bytes] = deque()
        self._position = 0

    def writable(self) -> bool:
        return True

    def write(self, data: bytes | bytearray | memoryview) -> int:  # type: ignore[override]
        self._chunks.append(bytes(data))
        self._position += len(data)
        return len(data)

    def tell(self) -> int:
        return self._position

    def drain(self) -> bytes:
        """Everything written since the last call."""
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def _read_chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(ZIP_CHUNK_BYTES):
        yield chunk


def _pending(sink: _Sink) -> Iterator[bytes]:
    """The sink's content if there is any."""
    data = sink.drain()
    if data:
        yield data


def stream_zip(storage: Storage, plan: ZipPlan) -> Iterator[bytes]:
    """Yield the ZIP archive piece by piece; files are never read whole (ADR-008).

    A file that vanished from storage is left out instead of failing the whole download.
    """
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as archive:
        for name, key in plan.entries:
            try:
                source = storage.open(key)
            except FileNotFoundError:
                continue
            with source, archive.open(zipfile.ZipInfo(name), "w", force_zip64=True) as target:
                for chunk in _read_chunks(source):
                    target.write(chunk)
                    yield from _pending(sink)
        archive.writestr(MANIFEST_NAME, plan.manifest)
        yield from _pending(sink)
    yield from _pending(sink)  # the central directory, written when the archive closes


class BatchDownloads:
    """Prepares downloads; the API streams the results."""

    def __init__(self, ctx: BatchContext, queries: BatchQueries) -> None:
        self._ctx = ctx
        self._queries = queries

    def video(self, batch_id: UUID, row_number: int) -> tuple[str, BinaryIO]:
        """(file name, open stream) of one rendered video."""
        row = self._queries.row(batch_id, row_number)
        if row.status != "COMPLETED" or row.output_key is None:
            raise StateConflictError(StateConflictError.INVALID_STATE)
        try:
            return output_file_name(row.voter_id), self._ctx.storage.open(row.output_key)
        except FileNotFoundError:
            raise BatchNotFoundError from None

    def zip_plan(self, batch_id: UUID) -> ZipPlan:
        """Entries for every completed video plus the manifest (A7)."""
        entries: list[tuple[str, str]] = []
        manifest = [MANIFEST_HEADER]
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            for row in uow.batches.iter_rows(batch_id):
                name = output_file_name(row.voter_id) if row.output_key else ""
                if row.status == "COMPLETED" and row.output_key:
                    entries.append((name, row.output_key))
                manifest.append(
                    [
                        str(row.row_number),
                        neutralise_cell(row.name),
                        neutralise_cell(row.voter_id),
                        row.status,
                        name,
                        row.failure_code or "",
                        _message(row),
                        "" if row.render_seconds is None else f"{row.render_seconds:.2f}",
                    ]
                )
        if not entries:
            raise DomainError(FailureCode.NO_COMPLETED_ROWS)
        return ZipPlan(entries, _csv_text(manifest))

    def failures_csv(self, batch_id: UUID) -> str:
        """Failed and skipped rows with code and plain message; formulas are neutralised."""
        table = [FAILURE_HEADER]
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            for row in uow.batches.iter_rows(batch_id, FAILED_STATUSES):
                table.append(
                    [
                        str(row.row_number),
                        neutralise_cell(row.name),
                        neutralise_cell(row.voter_id),
                        row.status,
                        row.failure_code or "",
                        _message(row),
                    ]
                )
        return _csv_text(table)
