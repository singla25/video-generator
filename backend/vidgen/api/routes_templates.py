"""Template endpoints: upload, consent, analysis, slot (AC1, AC5, AC6, AC18)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from vidgen.api.deps import container, require_csrf
from vidgen.api.errors import VALIDATION_ERROR, ApiError
from vidgen.api.schemas import SlotRequest, template_json
from vidgen.api.uploads import PAYLOAD_TOO_LARGE, UploadTooLargeError, read_upload
from vidgen.domain.codes import FailureCode, plain_message

router = APIRouter(prefix="/templates", tags=["templates"], dependencies=[Depends(require_csrf)])
_TICKED = frozenset({"true", "1", "on", "yes"})


def _too_large(code: FailureCode) -> ApiError:
    """413 with the plain message of ``code``."""
    return ApiError(PAYLOAD_TOO_LARGE, code.value, plain_message(code))


@router.post("", status_code=201)
async def upload_template(request: Request) -> dict[str, Any]:
    """Upload a template video and the word to replace (``original_name``)."""
    app = container(request)
    try:
        async with read_upload(request, max_file_bytes=app.settings.max_video_bytes) as form:
            video = form.files.get("video")
            if video is None:
                raise ApiError(422, VALIDATION_ERROR)
            created = await run_in_threadpool(
                app.templates.upload_template, video, form.fields.get("original_name", "")
            )
    except UploadTooLargeError:
        raise _too_large(FailureCode.UNSUPPORTED_VIDEO) from None
    return template_json(created)


@router.get("")
def list_templates(request: Request) -> dict[str, Any]:
    """All templates."""
    return {"templates": [template_json(t) for t in container(request).templates.list_templates()]}


@router.get("/{template_id}")
def get_template(template_id: UUID, request: Request) -> dict[str, Any]:
    """One template with its profile."""
    return template_json(container(request).templates.get(template_id))


@router.post("/{template_id}/consent")
async def upload_consent(template_id: UUID, request: Request) -> JSONResponse:
    """Upload the consent file together with the confirmation tick (C1)."""
    app = container(request)
    try:
        async with read_upload(request, max_file_bytes=app.settings.max_consent_bytes) as form:
            ticked = form.fields.get("confirmed", "").strip().lower() in _TICKED
            template = await run_in_threadpool(
                app.templates.attach_consent, template_id, form.files.get("file"), ticked
            )
    except UploadTooLargeError:
        raise _too_large(FailureCode.CONSENT_FILE_INVALID) from None
    return JSONResponse(template_json(template))


@router.post("/{template_id}/analyse")
def analyse(template_id: UUID, request: Request, force: bool = False) -> dict[str, Any]:
    """Find the slot with speech-to-text (a stored result is reused unless ``force``)."""
    return template_json(container(request).templates.analyse(template_id, force=force))


@router.put("/{template_id}/slot")
def set_slot(template_id: UUID, body: SlotRequest, request: Request) -> dict[str, Any]:
    """Set the slot manually; it must be confirmed again."""
    return template_json(
        container(request).templates.set_slot(template_id, body.start_s, body.end_s)
    )


@router.post("/{template_id}/slot/confirm")
def confirm_slot(template_id: UUID, request: Request) -> dict[str, Any]:
    """Confirm the current slot."""
    return template_json(container(request).templates.confirm_slot(template_id))
