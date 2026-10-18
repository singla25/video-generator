"""Test doubles for the API tests. Independent of the backend's own fakes (ADR-008)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from PIL import Image

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.values import Word
from vidgen.infrastructure.storage.local import StorageError
from vidgen.ports.models import VideoInfo

CHUNK = 64 * 1024
VALID_VIDEO = b"FAKEVIDEO" + bytes(2000)
UNSUPPORTED_VIDEO = b"WEBM" + bytes(2000)
DURATION_S = 4.0

# Names and IDs that must never show up in logs, audit entries or error bodies.
CANARY_NAME = "Rajesh Canary-Kumar"
CANARY_ID = "RJ/12/097/CANARY1"


class FakeClock:
    """A settable UTC clock implementing the ``Clock`` port."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 10, 18, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    def advance(self, **kwargs: float) -> None:
        """Move time forward, e.g. ``advance(minutes=16)``."""
        self._now += timedelta(**kwargs)


class InMemoryStorage:
    """Storage double: never overwrites, counts consumed bytes, can be told to fail."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.bytes_consumed = 0
        self.fail_writes = False

    def write(self, key: str, data: BinaryIO) -> str:
        """Store a stream; a taken key gets a ``-2``, ``-3`` suffix."""
        if self.fail_writes:
            raise StorageError
        final = key
        number = 1
        while final in self.files:
            number += 1
            stem, dot, ext = key.rpartition(".")
            final = f"{stem}-{number}.{ext}" if dot else f"{key}-{number}"
        buffer = io.BytesIO()
        while chunk := data.read(CHUNK):
            self.bytes_consumed += len(chunk)
            buffer.write(chunk)
        self.files[final] = buffer.getvalue()
        return final

    def open(self, key: str) -> BinaryIO:
        """Open a stored file."""
        if key not in self.files:
            raise FileNotFoundError(key)
        return io.BytesIO(self.files[key])

    def delete(self, key: str) -> None:
        """Delete a stored file (missing keys are fine)."""
        self.files.pop(key, None)

    def exists(self, key: str) -> bool:
        """Return True if the key exists."""
        return key in self.files


class FakeVideoProbe:
    """Probe double: decides by the first bytes of the file, never runs ffprobe."""

    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.explode_with: Exception | None = None

    def probe(self, path: Path) -> VideoInfo:
        """Accept ``FAKEVIDEO...`` files, reject ``WEBM...`` and anything else."""
        self.calls.append(path)
        if self.explode_with is not None:
            raise self.explode_with
        head = path.read_bytes()[:9]
        if head.startswith(b"FAKEVIDEO"):
            return VideoInfo("mp4", "h264", "aac", 320, 240, 25.0, DURATION_S, path.stat().st_size)
        if head.startswith(b"WEBM"):
            raise DomainError(FailureCode.UNSUPPORTED_VIDEO)
        raise DomainError(FailureCode.CORRUPT_VIDEO)


class FakeSpeechToText:
    """STT double returning configured words, or raising."""

    def __init__(self, words: list[Word] | None = None) -> None:
        self.words = words if words is not None else []
        self.error: Exception | None = None
        self.calls = 0

    def transcribe(self, audio: Path) -> list[Word]:
        """Return the configured transcript."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.words)


def word(text: str, start: float, confidence: float = 0.95) -> Word:
    """A 0.4 s word."""
    return Word(text=text, start_s=start, end_s=round(start + 0.4, 6), confidence=confidence)


# ---- consent file bytes ---------------------------------------------------------------


def pdf_bytes(extra: bytes = b"") -> bytes:
    """A minimal well-formed PDF (header, one empty page, trailer, EOF marker)."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 10 10]>>endobj\n"
        + extra
        + b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )


def png_bytes() -> bytes:
    """A valid 8x8 PNG."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, "PNG")
    return buffer.getvalue()


def jpeg_bytes() -> bytes:
    """A valid 16x16 JPEG."""
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 120, 10)).save(buffer, "JPEG")
    return buffer.getvalue()
