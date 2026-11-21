"""Speech to text with faster-whisper (word timestamps, CPU int8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vidgen.domain.values import Word
from vidgen.infrastructure.local_ai._common import LazyModel, Loader, require_audio
from vidgen.infrastructure.local_ai.loaders import load_whisper

TRANSCRIBE_LANGUAGE = "hi"


class FasterWhisperSpeechToText:
    """``SpeechToText`` port backed by a lazily loaded faster-whisper model."""

    def __init__(self, weights_dir: Path, loader: Loader[Any] = load_whisper) -> None:
        self._model = LazyModel("speech-to-text", weights_dir, loader)

    def transcribe(self, audio: Path, hint: str | None = None) -> list[Word]:
        """Return words with start/end seconds and confidence; silence gives an empty list.

        A non-empty ``hint`` (the expected name) is passed to Whisper as ``hotwords``.
        """
        require_audio(audio)
        options: dict[str, Any] = {"language": TRANSCRIBE_LANGUAGE, "word_timestamps": True}
        if hint:
            options["hotwords"] = hint
        segments, _info = self._model.get().transcribe(str(audio), **options)
        return [
            Word(
                text=raw.word.strip(),
                start_s=float(raw.start),
                end_s=float(raw.end),
                confidence=float(raw.probability),
            )
            for segment in segments
            for raw in (segment.words or [])
        ]

    def warm_up(self) -> None:
        """Load the model now (no inference), so missing weights show at start-up."""
        self._model.get()

    def release(self) -> None:
        """Unload the model to free memory; it loads again on the next use."""
        self._model.release()
