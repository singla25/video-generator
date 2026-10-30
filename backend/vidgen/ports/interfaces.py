"""Protocols for every port named in ADR-008.

Signatures are sketches from the M1 plan; later slices may refine them.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol
from uuid import UUID

from vidgen.domain.timing import TimingPlan
from vidgen.domain.values import TextRegion, Word
from vidgen.ports.batches import BatchStore
from vidgen.ports.models import AuditEntry, SheetRow, TemplateRecord, VideoInfo


class SpeechToText(Protocol):
    """Transcribes audio into words with timestamps."""

    def transcribe(self, audio: Path) -> list[Word]:
        """Return the words with timestamps and confidence."""
        ...


class Transliterator(Protocol):
    """Converts a name between scripts for speaking."""

    def transliterate(self, text: str, target_script: str) -> str:
        """Return ``text`` written in ``target_script``."""
        ...


class VoiceCloner(Protocol):
    """Synthesises speech in the template speaker's voice."""

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        """Write speech to ``out`` and return its duration in seconds."""
        ...


class LipSyncer(Protocol):
    """Adjusts the mouth region of video frames to match new audio."""

    def sync(self, video: Path, audio: Path, out: Path) -> None:
        """Write the lip-synced video to ``out``."""
        ...


class TextDetector(Protocol):
    """Finds on-screen text (OCR). Port only in M1 (R2.2)."""

    def detect(self, video: Path) -> list[TextRegion]:
        """Return the text regions found in ``video``."""
        ...


class TextRenderer(Protocol):
    """Replaces on-screen name text in a video (R5). Port only in M1."""

    def render_text(self, video: Path, region: TextRegion, text: str, out: Path) -> None:
        """Write ``video`` with ``region`` redrawn as ``text`` to ``out``."""
        ...


class LabelRenderer(Protocol):
    """Renders the AI-generated disclosure label as an image."""

    def render_label(self, width: int, height: int, out: Path) -> None:
        """Write a PNG label band of the given size to ``out``."""
        ...


class VideoProbe(Protocol):
    """Checks an uploaded video from its content and describes it."""

    def probe(self, path: Path) -> VideoInfo:
        """Return facts about ``path`` or raise a coded DomainError if it is not acceptable."""
        ...


class VideoEncoder(Protocol):
    """Splices audio, overlays the label and writes the final video."""

    def render(
        self,
        template: Path,
        new_slot_audio: Path,
        slot: tuple[float, float],
        plan: TimingPlan,
        label_png: Path,
        metadata: Mapping[str, str],
        out: Path,
    ) -> None:
        """Splice ``new_slot_audio`` into the slot following ``plan`` and write ``out``."""
        ...


class QualityChecker(Protocol):
    """Checks a rendered output against quality rules."""

    def check(self, template: Path, output: Path) -> list[str]:
        """Return failure codes; an empty list means the output passed."""
        ...


class Storage(Protocol):
    """Stores files without ever overwriting existing ones."""

    def write(self, key: str, data: BinaryIO) -> str:
        """Atomically store a stream and return the final key."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open a stored file for streaming reads."""
        ...

    def delete(self, key: str) -> None:
        """Delete a stored file."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if ``key`` exists."""
        ...

    def folder_exists(self, folder: str) -> bool:
        """Return True if ``folder`` already exists, so a new batch must not reuse it (R6.2)."""
        ...


class SheetReader(Protocol):
    """Streams rows from a spreadsheet file."""

    def headers(self, path: Path) -> list[str]:
        """Return the header cells of the first worksheet."""
        ...

    def rows(self, path: Path) -> Iterator[list[str]]:
        """Yield non-blank data rows one at a time."""
        ...

    def numbered_rows(self, path: Path) -> Iterator[SheetRow]:
        """Yield non-blank data rows with their true sheet row numbers."""
        ...

    def sheet_name(self, path: Path) -> str | None:
        """Return the worksheet name used, or None for CSV."""
        ...


class Cipher(Protocol):
    """Encrypts personal data and builds searchable blind indexes."""

    def encrypt(self, plaintext: str) -> bytes:
        """Return the ciphertext of ``plaintext``."""
        ...

    def decrypt(self, ciphertext: bytes) -> str:
        """Return the plaintext of ``ciphertext``."""
        ...

    def blind_index(self, value: str) -> str:
        """Return a keyed, deterministic index for ``value``."""
        ...


class TemplateRepository(Protocol):
    """Persistence for template profiles and their consent records."""

    def get(self, template_id: UUID) -> TemplateRecord | None:
        """Return the template or None."""
        ...

    def list(self) -> list[TemplateRecord]:
        """Return all templates, oldest first."""
        ...

    def add(self, campaign_id: UUID, template: TemplateRecord) -> None:
        """Persist a new template."""
        ...

    def save(self, template: TemplateRecord) -> None:
        """Persist changes to an existing template."""
        ...

    def add_consent(
        self, campaign_id: UUID, template_id: UUID, file_key: str, content_type: str
    ) -> None:
        """Record a confirmed consent file for a template."""
        ...


class AuditRepository(Protocol):
    """Append-only audit trail."""

    def add(
        self, *, campaign_id: UUID, actor: str, action: str, at: datetime, details: dict[str, Any]
    ) -> None:
        """Append an entry."""
        ...

    def list(self, *, campaign_id: UUID, action: str | None = None) -> list[AuditEntry]:
        """Return entries oldest first, optionally only one action."""
        ...


class UnitOfWork(Protocol):
    """One database transaction with the repositories that share it."""

    @property
    def campaign_id(self) -> UUID:
        """The campaign all writes belong to."""
        ...

    @property
    def templates(self) -> TemplateRepository:
        """Template persistence."""
        ...

    @property
    def audit(self) -> AuditRepository:
        """Audit persistence."""
        ...

    @property
    def batches(self) -> BatchStore:
        """Batch and row persistence."""
        ...

    def commit(self) -> None:
        """Commit the transaction."""
        ...


class Clock(Protocol):
    """Source of the current time, replaceable in tests."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        ...


class WorkerHeartbeat(Protocol):
    """A liveness signal the worker refreshes and the API reads."""

    def beat(self) -> None:
        """Record that a worker is alive now (never raises on a transient backend error)."""
        ...

    def is_alive(self) -> bool:
        """True while some worker has beaten recently; backend errors propagate."""
        ...
