"""The seam between the adapters and the remote service (ADR-013). No ``modal`` import here."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteModelClient(Protocol):
    """Remote calls the adapters need. Implementations raise the errors of ``errors.py``."""

    def transcribe(self, audio: bytes, hint: str | None = None) -> Any:
        """Return a list of ``{text, start_s, end_s, confidence}`` dicts (untrusted)."""
        ...

    def has_sample(self, sample_hash: str) -> bool:
        """True if the voice sample with this SHA-256 is already stored remotely."""
        ...

    def upload_sample(self, sample_hash: str, data: bytes) -> None:
        """Store the voice sample under its SHA-256."""
        ...

    def synthesize(self, text: str, sample_hash: str) -> bytes:
        """Return WAV bytes of ``text`` spoken in the voice of the stored sample."""
        ...
