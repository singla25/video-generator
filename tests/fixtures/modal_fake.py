"""In-memory fake of the remote model client (ADR-013). No network, no ``modal`` import."""

from __future__ import annotations

import io
import threading
import time
import wave
from typing import Any

DEMO_TOKEN = "demo-token-NOT-REAL-0000"  # noqa: S105 - synthetic marker for leak checks
SAMPLE_RATE = 16000


def make_wav_bytes(seconds: float = 1.0, rate: int = SAMPLE_RATE) -> bytes:
    """Return a mono 16-bit silent WAV of ``seconds`` length."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


def good_words() -> list[dict[str, Any]]:
    """Two demo words in the wire format the client returns."""
    return [
        {"text": "namaste", "start_s": 0.0, "end_s": 0.5, "confidence": 0.9},
        {"text": "Demo", "start_s": 0.5, "end_s": 1.0, "confidence": 0.8},
    ]


class FakeRemoteClient:
    """Implements the ``RemoteModelClient`` protocol in memory and records every call."""

    def __init__(self) -> None:
        self.samples: dict[str, bytes] = {}
        self.transcribe_calls: list[bytes] = []
        self.transcribe_hints: list[str | None] = []  # the hint of each transcribe call
        self.synthesize_calls: list[tuple[str, str]] = []
        self.upload_calls: list[str] = []
        self.has_sample_calls: list[str] = []
        self.words: Any = good_words()
        self.wav: bytes = make_wav_bytes(1.5)
        self.error: BaseException | None = None  # raised by every remote call when set
        self.upload_delay_s = 0.0
        self._lock = threading.Lock()

    def _maybe_fail(self) -> None:
        if self.error is not None:
            raise self.error

    def transcribe(self, audio: bytes, hint: str | None = None) -> Any:
        """Record the call and its hint; return the configured words."""
        self._maybe_fail()
        self.transcribe_calls.append(audio)
        self.transcribe_hints.append(hint)
        return self.words

    def has_sample(self, sample_hash: str) -> bool:
        """True once ``upload_sample`` stored this hash."""
        self._maybe_fail()
        self.has_sample_calls.append(sample_hash)
        return sample_hash in self.samples

    def upload_sample(self, sample_hash: str, data: bytes) -> None:
        """Store the sample (optionally slowly, to expose races)."""
        self._maybe_fail()
        time.sleep(self.upload_delay_s)
        with self._lock:
            self.upload_calls.append(sample_hash)
            self.samples[sample_hash] = data

    def synthesize(self, text: str, sample_hash: str) -> bytes:
        """Record (text, hash) and return the configured WAV bytes."""
        self._maybe_fail()
        self.synthesize_calls.append((text, sample_hash))
        return self.wav
