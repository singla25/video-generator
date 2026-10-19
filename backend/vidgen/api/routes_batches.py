"""Batch endpoints: creation, preview, start, control, status, rows (AC2, AC3, AC7, AC13, AC14)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse

from vidgen.api.deps import container, require_csrf
from vidgen.api.downloads import stream_file
from vidgen.api.errors import NOT_FOUND, VALIDATION_ERROR, ApiError
from vidgen.api.schemas_batches import (
    MappingBody,
    StartRequest,
    TemplateBody,
    batch_json,
    daily_json,
    report_json,
    rows_json,
    status_json,
)
from vidgen.api.uploads import PAYLOAD_TOO_LARGE, UploadTooLargeError, read_upload
from vidgen.domain.codes import FailureCode, plain_message
from vidgen.domain.status import RowStatus
from vidgen.services.batch_create import MappingRequest
from vidgen.services.batch_rules import page_count

router = APIRouter(prefix="/batches", tags=["batches"], dependencies=[Depends(require_csrf)])
stats_router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_csrf)])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_SEARCH_CHARS = 200
MAX_STATS_DAYS = 366
DEFAULT_STATS_DAYS = 30
PREVIEW_MEDIA_TYPE = "video/mp4"
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


def _text(value: str | None) -> str | None:
    """A trimmed form value, or None if it is empty."""
    stripped = (value or "").strip()
    return stripped or None


def _uuid(value: str) -> UUID:
    """Parse an id from a request body; a bad value is a validation error."""
    try:
        return UUID(value)
    except ValueError:
        raise ApiError(422, VALIDATION_ERROR) from None


@router.post("", status_code=201)
async def create_batch(request: Request) -> dict[str, Any]:
    """Upload a sheet, map its columns and create a draft batch with a validation report."""
    app = container(request)
    try:
        async with read_upload(request, max_file_bytes=app.settings.max_sheet_bytes) as form:
            sheet = form.files.get("sheet")
            name, id_ = _text(form.fields.get("name_column")), _text(form.fields.get("id_column"))
            raw_template = _text(form.fields.get("template_id"))
            if sheet is None or name is None or id_ is None or raw_template is None:
                raise ApiError(422, VALIDATION_ERROR)
            mapping = MappingRequest(name, id_, _text(form.fields.get("spoken_name_column")))
            view = await run_in_threadpool(app.batches.create, sheet, _uuid(raw_template), mapping)
    except UploadTooLargeError:
        code = FailureCode.UNSUPPORTED_SHEET
        raise ApiError(PAYLOAD_TOO_LARGE, code.value, plain_message(code)) from None
    return batch_json(view)


@router.get("")
def list_batches(
    request: Request, page: Page = 1, page_size: PageSize = DEFAULT_PAGE_SIZE
) -> dict[str, Any]:
    """Batch history, newest first."""
    views, total = container(request).batches.history(page, page_size)
    return {
        "batches": [batch_json(v) for v in views],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": page_count(total, page_size),
    }


@router.get("/{batch_id}")
def get_batch(batch_id: UUID, request: Request) -> dict[str, Any]:
    """One batch."""
    return batch_json(container(request).batches.get(batch_id))


@router.get("/{batch_id}/report")
def get_report(batch_id: UUID, request: Request) -> dict[str, Any]:
    """The validation report."""
    return report_json(container(request).batches.report(batch_id))


@router.get("/{batch_id}/status")
def get_status(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Counts, progress, ETA and failure breakdown."""
    return status_json(container(request).batches.status(batch_id))


@router.get("/{batch_id}/rows")
def get_rows(
    batch_id: UUID,
    request: Request,
    status: RowStatus | None = None,
    search: Annotated[str | None, Query(max_length=MAX_SEARCH_CHARS)] = None,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Rows with status filter, search and paging."""
    status_value = None if status is None else status.value
    result = container(request).batches.rows(batch_id, status_value, search, page, page_size)
    return rows_json(result)


@router.put("/{batch_id}/mapping")
def change_mapping(batch_id: UUID, body: MappingBody, request: Request) -> dict[str, Any]:
    """Choose other columns; rows are validated again."""
    mapping = MappingRequest(body.name_column, body.id_column, _text(body.spoken_name_column))
    return batch_json(container(request).batches.change_mapping(batch_id, mapping))


@router.put("/{batch_id}/template")
def change_template(batch_id: UUID, body: TemplateBody, request: Request) -> dict[str, Any]:
    """Use another usable template."""
    template_id = _uuid(body.template_id)
    return batch_json(container(request).batches.change_template(batch_id, template_id))


@router.post("/{batch_id}/preview", status_code=202)
def request_preview(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Queue the preview render of the first valid row."""
    return batch_json(container(request).batches.request_preview(batch_id))


@router.post("/{batch_id}/preview/approve")
def approve_preview(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Approve the rendered preview."""
    return batch_json(container(request).batches.approve_preview(batch_id))


@router.get("/{batch_id}/preview")
def download_preview(batch_id: UUID, request: Request) -> StreamingResponse:
    """The rendered preview video."""
    app = container(request)
    key = app.batches.preview_key(batch_id)
    try:
        stream = app.storage.open(key)
    except FileNotFoundError:
        raise ApiError(404, NOT_FOUND) from None
    return StreamingResponse(stream_file(stream), media_type=PREVIEW_MEDIA_TYPE)


@router.post("/{batch_id}/start")
def start_batch(
    batch_id: UUID,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
    body: StartRequest | None = None,
) -> dict[str, Any]:
    """Start the batch; ``Idempotency-Key`` makes repeating the call safe."""
    key = _text(idempotency_key)
    if key is None:
        raise ApiError(422, VALIDATION_ERROR)
    folder = None if body is None else body.folder_name
    return batch_json(container(request).batches.start(batch_id, key, folder))


@router.post("/{batch_id}/pause")
def pause_batch(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Pause the batch."""
    return batch_json(container(request).batches.pause(batch_id))


@router.post("/{batch_id}/resume")
def resume_batch(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Resume the batch."""
    return batch_json(container(request).batches.resume(batch_id))


@router.post("/{batch_id}/cancel")
def cancel_batch(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Cancel the batch (rows in progress finish)."""
    return batch_json(container(request).batches.cancel(batch_id))


@router.post("/{batch_id}/retry-failed")
def retry_failed(batch_id: UUID, request: Request) -> dict[str, Any]:
    """Queue the failed rows again."""
    return batch_json(container(request).batches.retry_failed(batch_id))


@router.delete("/{batch_id}", status_code=204)
def delete_batch(batch_id: UUID, request: Request) -> Response:
    """Delete the batch, its rows and its files."""
    container(request).batches.delete(batch_id)
    return Response(status_code=204)


@stats_router.get("/daily")
def daily_stats(
    request: Request,
    days: Annotated[int, Query(ge=1, le=MAX_STATS_DAYS)] = DEFAULT_STATS_DAYS,
) -> dict[str, Any]:
    """Completed videos per UTC day with the mean render time."""
    return daily_json(container(request).batches.daily(days))
