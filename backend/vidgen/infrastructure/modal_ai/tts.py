"""``VoiceCloner`` port backed by a remote voice-cloning function (ADR-013)."""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import wave
from pathlib import Path

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.local_ai._common import atomic_output, require_audio
from vidgen.infrastructure.modal_ai._guard import call_remote
from vidgen.infrastructure.modal_ai.client import RemoteModelClient

logger = logging.getLogger(__name__)

HASH_CHUNK_BYTES = 1024 * 1024


def sha256_of(path: Path) -> str:
    """Stream the file through SHA-256."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def wav_duration(data: bytes) -> float:
    """Seconds of WAV ``data``; empty, garbled or zero-length audio is ``TTS_FAILED``."""
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            frames, rate = handle.getnframes(), handle.getframerate()
    except (wave.Error, EOFError):
        raise DomainError(FailureCode.TTS_FAILED) from None
    if frames == 0 or rate == 0:
        raise DomainError(FailureCode.TTS_FAILED)
    return frames / rate


class ModalVoiceCloner:
    """Uploads the voice sample once, then sends only text and its hash per row."""

    def __init__(self, client: RemoteModelClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._known: set[str] = set()
        self.bytes_sent = 0
        self.bytes_received = 0

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        """Write the cloned speech to ``out`` (WAV, atomically); return its seconds."""
        require_audio(voice_sample)
        sample_hash = sha256_of(voice_sample)
        self._ensure_uploaded(sample_hash, voice_sample)
        wav = call_remote(lambda: self._client.synthesize(text, sample_hash))
        seconds = wav_duration(wav)  # validate before anything is written
        with atomic_output(out) as tmp:
            tmp.write_bytes(wav)
        self.bytes_sent += len(text.encode("utf-8")) + len(sample_hash)
        self.bytes_received += len(wav)
        logger.debug("remote synthesize done", extra={"seconds": seconds})
        return seconds

    def _ensure_uploaded(self, sample_hash: str, sample: Path) -> None:
        """Upload the sample if the remote lacks it; serialised so it happens once."""
        with self._lock:
            if sample_hash in self._known:
                return
            if not call_remote(lambda: self._client.has_sample(sample_hash)):
                data = sample.read_bytes()
                call_remote(lambda: self._client.upload_sample(sample_hash, data))
                self.bytes_sent += len(data)
            self._known.add(sample_hash)
