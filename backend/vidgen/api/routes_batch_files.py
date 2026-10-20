"""Download endpoints: single video, streamed ZIP, failures CSV (AC15)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response, StreamingResponse

from vidgen.api.deps import container, require_csrf
from vidgen.api.downloads import attachment_header
from vidgen.api.video_response import video_response
from vidgen.services.batch_downloads import stream_zip

router = APIRouter(prefix="/batches", tags=["downloads"], dependencies=[Depends(require_csrf)])
ZIP_TYPE = "application/zip"
CSV_TYPE = "text/csv; charset=utf-8"


@router.get("/{batch_id}/rows/{row_number}/video")
def download_video(
    batch_id: UUID,
    row_number: int,
    request: Request,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    """One rendered video; byte ranges are supported."""
    name, stream = container(request).batches.video(batch_id, row_number)
    headers = {"Content-Disposition": attachment_header(name)}
    return video_response(stream, range_header, headers=headers)


@router.get("/{batch_id}/download.zip")
def download_zip(batch_id: UUID, request: Request) -> StreamingResponse:
    """All completed videos plus the manifest, streamed."""
    app = container(request)
    plan = app.batches.zip_plan(batch_id)
    headers = {"Content-Disposition": attachment_header(f"batch-{batch_id}.zip")}
    return StreamingResponse(stream_zip(app.storage, plan), media_type=ZIP_TYPE, headers=headers)


@router.get("/{batch_id}/failures.csv")
def download_failures(batch_id: UUID, request: Request) -> Response:
    """Failed and skipped rows with their reasons."""
    text = container(request).batches.failures_csv(batch_id)
    headers = {"Content-Disposition": attachment_header(f"failures-{batch_id}.csv")}
    return Response(text, media_type=CSV_TYPE, headers=headers)
