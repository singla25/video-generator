"""``SpeechToText`` port backed by a remote Whisper function (ADR-013)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.values import Word
from vidgen.infrastructure.local_ai._common import require_audio
from vidgen.infrastructure.modal_ai._guard import call_remote
from vidgen.infrastructure.modal_ai.client import RemoteModelClient

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0


def _number(value: Any) -> float:
    """Return ``value`` as float; booleans and non-numbers are rejected."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("not a number")
    return float(value)


def _parse_word(raw: Any) -> Word:
    """Validate one remote word dict and map it to the domain."""
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
        raise ValueError("bad word")
    start, end, conf = (_number(raw.get(k)) for k in ("start_s", "end_s", "confidence"))
    if start < 0 or end < start or not MIN_CONFIDENCE <= conf <= MAX_CONFIDENCE:
        raise ValueError("bad word range")
    return Word(raw["text"], start, end, conf)


def parse_words(raw: Any) -> list[Word]:
    """Map the untrusted remote result to words; any problem is a coded ``STT_FAILED``."""
    try:
        if not isinstance(raw, list):
            raise ValueError("not a list")
        return [_parse_word(item) for item in raw]
    except ValueError:
        raise DomainError(FailureCode.STT_FAILED) from None


class ModalSpeechToText:
    """Sends the audio to the remote function and returns validated words."""

    def __init__(self, client: RemoteModelClient) -> None:
        self._client = client
        self.bytes_sent = 0
        self.bytes_received = 0

    def transcribe(self, audio: Path) -> list[Word]:
        """Return words with timestamps; silence gives an empty list."""
        require_audio(audio)
        data = audio.read_bytes()  # call-sized clips only (ADR-013 Q2)
        raw = call_remote(lambda: self._client.transcribe(data))
        self.bytes_sent += len(data)
        words = parse_words(raw)
        self.bytes_received += len(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
        logger.debug("remote transcribe done", extra={"word_count": len(words)})
        return words
