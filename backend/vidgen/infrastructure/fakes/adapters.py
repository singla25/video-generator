"""Fake speech-to-text, voice, lip sync and quality check.

Everything here is deterministic. The outputs are structurally valid (a real WAV, an unchanged
video) but carry a placeholder voice; real models arrive in M2.
"""

from __future__ import annotations

import array
import shutil
import wave
from pathlib import Path

from vidgen.domain.values import Word

SAMPLE_RATE = 16000
BASE_SECONDS = 0.30
SECONDS_PER_CHARACTER = 0.05
TONE_HALF_PERIOD_SAMPLES = 20
TONE_LEVEL = 8000


class FakeSpeechToText:
    """Returns the words it was given; by default none, so the slot must be marked by hand."""

    def __init__(self, words: list[Word] | None = None) -> None:
        self._words = list(words or [])

    def transcribe(self, audio: Path) -> list[Word]:
        """Return the configured transcript."""
        return list(self._words)


class FakeTransliterator:
    """Returns the text unchanged (the spoken name is then the written name)."""

    def transliterate(self, text: str, target_script: str) -> str:
        """Return ``text`` as given."""
        return text


class FakeVoiceCloner:
    """Writes a square-wave tone whose length grows with the length of the text."""

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        """Write the tone to ``out`` and return its duration in seconds."""
        seconds = BASE_SECONDS + SECONDS_PER_CHARACTER * len(text)
        count = int(seconds * SAMPLE_RATE)
        samples = array.array(
            "h",
            [
                TONE_LEVEL if (index // TONE_HALF_PERIOD_SAMPLES) % 2 else -TONE_LEVEL
                for index in range(count)
            ],
        )
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(samples.tobytes())
        return count / SAMPLE_RATE


class FakeLipSyncer:
    """Passes the frames through unchanged."""

    def sync(self, video: Path, audio: Path, out: Path, start_s: float = 0.0) -> None:
        """Copy ``video`` to ``out``; ``start_s`` is accepted and ignored."""
        shutil.copyfile(video, out)


class FakeQualityChecker:
    """Accepts every output (the real checks Q1-Q6 come in M2)."""

    def check(self, template: Path, output: Path) -> list[str]:
        """Return no failures."""
        return []
