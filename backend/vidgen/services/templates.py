"""Template use cases: upload, consent, analysis, slot (AC1, AC5, AC6, AC18).

No web framework is imported here; the API layer passes in plain values and file paths.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.slot_match import select_target_word, validate_slot
from vidgen.ports import Clock, SpeechToText, Storage, TemplateRecord, UnitOfWork, VideoProbe
from vidgen.services.audit import ACTOR_ADMIN, UowFactory
from vidgen.services.errors import InvalidInputError, PreconditionError, TemplateNotFoundError

logger = logging.getLogger(__name__)

SLOT_AUTO = "AUTO"
SLOT_MANUAL = "MANUAL"
VIDEO_KEY = "templates/{id}/video.mp4"
CONSENT_KEY = "templates/{id}/consent-{token}.{ext}"
CONSENT_EXTENSIONS = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}
ConsentSniffer = Callable[[Path], str | None]


class TemplateService:
    """Orchestrates templates using ports only."""

    def __init__(
        self,
        *,
        uow: UowFactory,
        storage: Storage,
        probe: VideoProbe,
        stt: SpeechToText,
        clock: Clock,
        confidence_threshold: float,
        sniff_consent: ConsentSniffer,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._probe = probe
        self._stt = stt
        self._clock = clock
        self._threshold = confidence_threshold
        self._sniff_consent = sniff_consent

    # ---- reads -------------------------------------------------------------------------

    def get(self, template_id: UUID) -> TemplateRecord:
        """Return a template or raise TemplateNotFoundError."""
        with self._uow() as uow:
            return self._load(uow, template_id)

    def list_templates(self) -> list[TemplateRecord]:
        """All templates, oldest first."""
        with self._uow() as uow:
            return uow.templates.list()

    # ---- commands ----------------------------------------------------------------------

    def upload_template(self, video: Path, original_name: str) -> TemplateRecord:
        """Check, store and register a template video (AC1, D-13)."""
        name = original_name.strip()
        if not name:
            raise InvalidInputError("original_name is required")
        info = self._probe.probe(video)  # DomainError for unsupported / corrupt files
        template_id = uuid4()
        key = VIDEO_KEY.format(id=template_id)
        with video.open("rb") as handle:
            stored_key = self._storage.write(key, handle)
        try:
            record = TemplateRecord(
                id=template_id,
                video_key=stored_key,
                original_name=name,
                duration_s=info.duration_s,
                width=info.width,
                height=info.height,
            )
            with self._uow() as uow:
                uow.templates.add(uow.campaign_id, record)
                self._audit(
                    uow,
                    "TEMPLATE_UPLOADED",
                    template_id=str(template_id),
                    size_bytes=info.size_bytes,
                )
                uow.commit()
                return uow.templates.get(template_id) or record
        except BaseException:
            self._storage.delete(stored_key)  # no orphan file when the database step fails
            raise

    def attach_consent(
        self, template_id: UUID, file: Path | None, confirmed: bool
    ) -> TemplateRecord:
        """Store a consent file and mark the template consented (AC5, C1)."""
        if not confirmed or file is None:
            raise DomainError(FailureCode.CONSENT_MISSING)
        content_type = self._sniff_consent(file)
        if content_type is None:
            raise DomainError(FailureCode.CONSENT_FILE_INVALID)
        with self._uow() as uow:
            template = self._load(uow, template_id)
            key = CONSENT_KEY.format(
                id=template_id, token=uuid4().hex[:12], ext=CONSENT_EXTENSIONS[content_type]
            )
            with file.open("rb") as handle:
                stored_key = self._storage.write(key, handle)
            try:
                template.consent_confirmed = True
                uow.templates.save(template)
                uow.templates.add_consent(uow.campaign_id, template_id, stored_key, content_type)
                self._audit(
                    uow, "CONSENT_UPLOADED", template_id=str(template_id), content_type=content_type
                )
                uow.commit()
            except BaseException:
                self._storage.delete(stored_key)  # no orphan consent file
                raise
            return template

    def analyse(self, template_id: UUID, *, force: bool = False) -> TemplateRecord:
        """Find the original name's slot with speech-to-text; reuse the stored result (AC6)."""
        with self._uow() as uow:
            template = self._load(uow, template_id)
            if template.analysed_at is not None and not force:
                return template
            words = self._transcribe(template)
            found = select_target_word(words, template.original_name, self._threshold)
            template.analysed_at = self._clock.now()
            template.slot_confirmed = False
            if found is None:
                template.slot_start_s = template.slot_end_s = None
                template.slot_source = template.slot_confidence = None
                template.slot_error = FailureCode.SLOT_NOT_FOUND.value
            else:
                template.slot_start_s, template.slot_end_s = found.start_s, found.end_s
                template.slot_source = SLOT_AUTO
                template.slot_confidence = found.confidence
                template.slot_error = None
            uow.templates.save(template)
            self._audit(
                uow, "TEMPLATE_ANALYSED", template_id=str(template_id), found=found is not None
            )
            uow.commit()
            return template

    def set_slot(self, template_id: UUID, start_s: float, end_s: float) -> TemplateRecord:
        """Set a manual slot; it must be confirmed again (A5, AC18)."""
        with self._uow() as uow:
            template = self._load(uow, template_id)
            validate_slot(start_s, end_s, template.duration_s)
            template.slot_start_s, template.slot_end_s = start_s, end_s
            template.slot_source = SLOT_MANUAL
            template.slot_confidence = None
            template.slot_error = None
            template.slot_confirmed = False
            uow.templates.save(template)
            self._audit(uow, "SLOT_SET", template_id=str(template_id), source=SLOT_MANUAL)
            uow.commit()
            return template

    def confirm_slot(self, template_id: UUID) -> TemplateRecord:
        """Confirm the current slot; the pipeline may change only this range (C6)."""
        with self._uow() as uow:
            template = self._load(uow, template_id)
            if template.slot is None:
                raise PreconditionError(FailureCode.SLOT_NOT_FOUND)
            template = replace(template, slot_confirmed=True)
            uow.templates.save(template)
            self._audit(uow, "SLOT_CONFIRMED", template_id=str(template_id))
            uow.commit()
            return template

    # ---- helpers -----------------------------------------------------------------------

    @staticmethod
    def _load(uow: UnitOfWork, template_id: UUID) -> TemplateRecord:
        template = uow.templates.get(template_id)
        if template is None:
            raise TemplateNotFoundError
        return template

    def _audit(self, uow: UnitOfWork, action: str, **details: Any) -> None:
        uow.audit.add(
            campaign_id=uow.campaign_id,
            actor=ACTOR_ADMIN,
            action=action,
            at=self._clock.now(),
            details=details,
        )

    def _transcribe(self, template: TemplateRecord) -> list[Any]:
        """Run speech-to-text on a temporary copy of the stored video (STT_FAILED on error)."""
        with tempfile.NamedTemporaryFile(suffix=".mp4") as scratch:
            with self._storage.open(template.video_key) as source:
                shutil.copyfileobj(source, scratch)
            scratch.flush()
            try:
                return list(self._stt.transcribe(Path(scratch.name)))
            except Exception as exc:
                # Only the exception type is logged: its text could contain personal data.
                logger.error("speech-to-text failed", extra={"error_type": type(exc).__name__})
                raise DomainError(FailureCode.STT_FAILED) from exc
