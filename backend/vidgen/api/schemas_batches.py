"""JSON views of batches, reports, status and rows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from vidgen.domain.stats import StatusCounts
from vidgen.ports.batches import DayStat, RowView
from vidgen.services.batch_queries import failure_message
from vidgen.services.batch_views import BatchReport, BatchStatus, BatchView, RowsPage

MAX_FOLDER_INPUT_CHARS = 1000
MAX_COLUMN_CHARS = 500


class StartRequest(BaseModel):
    """Optional body of the start request."""

    folder_name: str | None = Field(default=None, max_length=MAX_FOLDER_INPUT_CHARS)


class MappingBody(BaseModel):
    """Body of the mapping change."""

    name_column: str = Field(min_length=1, max_length=MAX_COLUMN_CHARS)
    id_column: str = Field(min_length=1, max_length=MAX_COLUMN_CHARS)
    spoken_name_column: str | None = Field(default=None, max_length=MAX_COLUMN_CHARS)


class TemplateBody(BaseModel):
    """Body of the template switch."""

    template_id: str


def counts_json(counts: StatusCounts) -> dict[str, int]:
    """The seven overview counts."""
    return {
        "total": counts.total,
        "completed": counts.completed,
        "processing": counts.processing,
        "queued": counts.queued,
        "failed": counts.failed,
        "skipped": counts.skipped,
        "cancelled": counts.cancelled,
    }


def report_json(report: BatchReport) -> dict[str, Any]:
    """Validation report."""
    return {
        "total_rows": report.total_rows,
        "valid_rows": report.valid_rows,
        "skipped_rows": report.skipped_rows,
        "problems": [
            {"row_number": p.row_number, "code": p.code, "message": p.message, "faults": p.faults}
            for p in report.problems
        ],
    }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def batch_json(view: BatchView) -> dict[str, Any]:
    """A batch with counts and its preview state."""
    record = view.record
    body: dict[str, Any] = {
        "id": str(record.id),
        "template_id": str(record.template_id),
        "status": record.status,
        "created_at": _iso(record.created_at),
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
        "folder_name": record.folder_name,
        "sheet_name": record.sheet_name,
        "preview": {"status": view.preview_status, "approved": view.preview_approved},
        "counts": counts_json(view.counts),
        "success_rate": view.success_rate,
    }
    if view.report is not None:
        body["report"] = report_json(view.report)
    if view.queued_rows is not None:
        body["queued_rows"] = view.queued_rows
    if view.retried_rows is not None:
        body["retried_rows"] = view.retried_rows
    return body


def status_json(status: BatchStatus) -> dict[str, Any]:
    """Live status."""
    return {
        "counts": counts_json(status.counts),
        "progress_percent": status.progress_percent,
        "eta_seconds": status.eta_seconds,
        "failures": [
            {"code": f.code, "count": f.count, "message": f.message} for f in status.failures
        ],
    }


def row_json(row: RowView) -> dict[str, Any]:
    """One row for the admin (names and IDs are decrypted here, B6)."""
    return {
        "row_number": row.row_number,
        "name": row.name,
        "voter_id": row.voter_id,
        "spoken_name": row.spoken_name,
        "status": row.status,
        "failure_code": row.failure_code,
        "message": failure_message(row.failure_code) if row.failure_code else None,
        "render_seconds": row.render_seconds,
        "has_video": row.output_key is not None,
    }


def rows_json(page: RowsPage) -> dict[str, Any]:
    """A page of rows."""
    return {
        "rows": [row_json(r) for r in page.rows],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": page.total_pages,
        "counts": counts_json(page.counts),
        "progress_percent": page.progress_percent,
    }


def daily_json(series: list[tuple[date, DayStat]]) -> dict[str, Any]:
    """Videos per day."""
    return {
        "days": [
            {
                "date": day.isoformat(),
                "videos": s.videos,
                "avg_render_seconds": s.avg_render_seconds,
            }
            for day, s in series
        ]
    }
