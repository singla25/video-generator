"""Batch creation: sheet ingestion, validation report, mapping and template changes (AC2, AC3)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.headers import resolve_mapping
from vidgen.domain.status import BatchState
from vidgen.domain.validation import RowInput, RowRules, RowValidator, RowVerdict
from vidgen.ports.batches import BatchRecord, MappingRecord, NewBatchRow
from vidgen.ports.models import SheetRow
from vidgen.services.batch_support import (
    BatchContext,
    audit,
    describe,
    ensure_usable,
    load_batch,
    load_template,
)
from vidgen.services.batch_views import BatchReport, BatchView, Problem
from vidgen.services.errors import StateConflictError

STATUS_QUEUED = "QUEUED"
STATUS_SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class MappingRequest:
    """The user's column choices, by header text."""

    name_column: str
    id_column: str
    spoken_name_column: str | None = None


class ReportBuilder:
    """Collects validation verdicts into the report of a sheet."""

    def __init__(self) -> None:
        self.total = 0
        self.skipped = 0
        self.problems: list[Problem] = []

    def add(self, verdict: RowVerdict) -> None:
        """Count one verdict."""
        self.total += 1
        if verdict.code is not None:
            self.skipped += 1
            faults = [fault.value for fault in verdict.faults]
            self.problems.append(
                Problem(verdict.row_number, verdict.code.value, verdict.message, faults)
            )

    def build(self) -> BatchReport:
        """The finished report."""
        return BatchReport(self.total, self.total - self.skipped, self.skipped, self.problems)


def _cell(cells: list[str], index: int | None) -> str:
    """A cell by index; short rows read as empty."""
    return cells[index] if index is not None and index < len(cells) else ""


class SheetIngest:
    """Reads a sheet with a column mapping and yields validated rows for storing."""

    def __init__(self, ctx: BatchContext, path: Path, request: MappingRequest) -> None:
        self._ctx = ctx
        self._path = path
        headers = ctx.reader.headers(path)  # UNSUPPORTED_SHEET for unreadable sheets
        found = resolve_mapping(
            headers,
            name=request.name_column,
            id_=request.id_column,
            spoken_name=request.spoken_name_column,
        )
        self.mapping = MappingRecord(
            request.name_column,
            request.id_column,
            request.spoken_name_column,
            found.name_index,
            found.id_index,
            found.spoken_name_index,
        )
        self.sheet_name = ctx.reader.sheet_name(path)
        self.report = ReportBuilder()

    def rows(self) -> Iterator[NewBatchRow]:
        """Validated rows in sheet order; fails if the sheet is empty or too long."""
        validator = RowValidator(RowRules(max_name_graphemes=self._ctx.max_name_graphemes))
        for row in self._limited(self._ctx.reader.numbered_rows(self._path)):
            row_input = self._input(row)
            verdict = validator.validate(row_input)
            self.report.add(verdict)
            yield self._stored(row_input, verdict)
        if self.report.total == 0:
            raise DomainError(FailureCode.UNSUPPORTED_SHEET)

    def _limited(self, rows: Iterator[SheetRow]) -> Iterator[SheetRow]:
        for count, row in enumerate(rows, start=1):
            if count > self._ctx.max_sheet_rows:
                raise DomainError(FailureCode.UNSUPPORTED_SHEET)
            yield row

    def _input(self, row: SheetRow) -> RowInput:
        m = self.mapping
        spoken = _cell(row.cells, m.spoken_name_index).strip()
        return RowInput(
            row.row_number,
            _cell(row.cells, m.name_index).strip(),
            _cell(row.cells, m.id_index).strip(),
            spoken or None,
        )

    @staticmethod
    def _stored(row: RowInput, verdict: RowVerdict) -> NewBatchRow:
        code = verdict.code.value if verdict.code else None
        status = STATUS_SKIPPED if code else STATUS_QUEUED
        return NewBatchRow(row.row_number, row.name, row.id_, row.spoken_name, status, code)


class BatchCreator:
    """Creates batches and re-targets drafts."""

    def __init__(self, ctx: BatchContext) -> None:
        self._ctx = ctx

    def create(self, sheet: Path, template_id: UUID, request: MappingRequest) -> BatchView:
        """Validate a sheet and create a draft batch from it."""
        ctx = self._ctx
        with ctx.uow() as uow:
            template = load_template(uow, template_id)
            ensure_usable(template)
            ingest = SheetIngest(ctx, sheet, request)
            batch_id = uuid4()
            with sheet.open("rb") as handle:
                sheet_key = ctx.storage.write(
                    f"batches/{batch_id}/sheet{sheet.suffix.lower()}", handle
                )
            try:
                record = BatchRecord(
                    id=batch_id,
                    template_id=template_id,
                    status=BatchState.DRAFT.value,
                    created_at=ctx.clock.now(),
                    sheet_key=sheet_key,
                    sheet_name=ingest.sheet_name,
                    mapping=ingest.mapping,
                )
                uow.batches.add(uow.campaign_id, record)
                uow.batches.replace_rows(uow.campaign_id, batch_id, ingest.rows())
                report = ingest.report.build()
                audit(
                    ctx,
                    uow,
                    "BATCH_CREATED",
                    batch_id=str(batch_id),
                    template_id=str(template_id),
                    total_rows=report.total_rows,
                    valid_rows=report.valid_rows,
                )
                uow.commit()
            except BaseException:
                ctx.storage.delete(sheet_key)  # no orphan sheet (it holds personal data)
                raise
            return describe(uow, record, report=report)

    def change_mapping(self, batch_id: UUID, request: MappingRequest) -> BatchView:
        """Re-read the stored sheet with other columns; the old approval stops applying (A5)."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            self._require_draft(batch)
            with self._stored_sheet(batch) as path:
                ingest = SheetIngest(ctx, path, request)
                uow.batches.replace_rows(uow.campaign_id, batch_id, ingest.rows())
            report = ingest.report.build()
            batch = replace(batch, mapping=ingest.mapping, sheet_name=ingest.sheet_name)
            uow.batches.save(batch)
            audit(ctx, uow, "BATCH_MAPPING_CHANGED", batch_id=str(batch_id))
            uow.commit()
            return describe(uow, batch, report=report)

    def change_template(self, batch_id: UUID, template_id: UUID) -> BatchView:
        """Use another (usable) template for a draft; the old approval stops applying (A5)."""
        ctx = self._ctx
        with ctx.uow() as uow:
            batch = load_batch(uow, batch_id, lock=True)
            self._require_draft(batch)
            ensure_usable(load_template(uow, template_id))
            batch = replace(batch, template_id=template_id)
            uow.batches.save(batch)
            audit(
                ctx,
                uow,
                "BATCH_TEMPLATE_CHANGED",
                batch_id=str(batch_id),
                template_id=str(template_id),
            )
            uow.commit()
            return describe(uow, batch)

    def report(self, batch_id: UUID) -> BatchReport:
        """Rebuild the validation report from the stored rows."""
        validator = RowValidator(RowRules(max_name_graphemes=self._ctx.max_name_graphemes))
        builder = ReportBuilder()
        with self._ctx.uow() as uow:
            load_batch(uow, batch_id)
            for row in uow.batches.iter_rows(batch_id):
                builder.add(
                    validator.validate(
                        RowInput(row.row_number, row.name, row.voter_id, row.spoken_name)
                    )
                )
        return builder.build()

    @staticmethod
    def _require_draft(batch: BatchRecord) -> None:
        if batch.status != BatchState.DRAFT.value:
            raise StateConflictError(StateConflictError.INVALID_STATE)

    def _stored_sheet(self, batch: BatchRecord) -> _TempSheet:
        return _TempSheet(self._ctx, batch.sheet_key or "")


class _TempSheet:
    """Context manager: the stored sheet copied to a temporary file with its extension."""

    def __init__(self, ctx: BatchContext, key: str) -> None:
        self._ctx = ctx
        self._key = key
        self._file: tempfile._TemporaryFileWrapper[bytes] | None = None

    def __enter__(self) -> Path:
        self._file = tempfile.NamedTemporaryFile(suffix=Path(self._key).suffix)
        with self._ctx.storage.open(self._key) as source:
            shutil.copyfileobj(source, self._file)
        self._file.flush()
        return Path(self._file.name)

    def __exit__(self, *_: object) -> None:
        if self._file is not None:
            self._file.close()
