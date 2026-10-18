"""Protocols for every port named in ADR-008.

Signatures are sketches from the M1 plan; later slices may refine them.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID

from vidgen.domain.values import TextRegion, Word


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


class VideoEncoder(Protocol):
    """Splices audio, overlays the label and writes the final video."""

    def probe(self, video: Path) -> dict[str, object]:
        """Return stream and format facts for ``video`` (via ffprobe)."""
        ...

    def render(
        self,
        template: Path,
        new_slot_audio: Path,
        slot: tuple[float, float],
        label: Path,
        metadata: dict[str, str],
        out: Path,
    ) -> None:
        """Render the output video for one row."""
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


class SheetReader(Protocol):
    """Streams rows from a spreadsheet file."""

    def headers(self, path: Path) -> list[str]:
        """Return the header cells of the first worksheet."""
        ...

    def rows(self, path: Path) -> Iterator[list[str]]:
        """Yield data rows one at a time."""
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


# TODO(T10): replace ``object`` with the real entity types.
class TemplateRepository(Protocol):
    """Persistence for template profiles."""

    def get(self, template_id: UUID) -> object | None:
        """Return the template or None."""
        ...

    def add(self, template: object) -> None:
        """Persist a new template."""
        ...


class BatchRepository(Protocol):
    """Persistence for batches and their rows."""

    def get(self, batch_id: UUID) -> object | None:
        """Return the batch or None."""
        ...

    def add(self, batch: object) -> None:
        """Persist a new batch."""
        ...

    def delete(self, batch_id: UUID) -> None:
        """Delete a batch with its rows."""
        ...


class Clock(Protocol):
    """Source of the current time, replaceable in tests."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        ...
