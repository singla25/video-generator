"""Stub model engines and helpers for the M2 adapter contract tests (no real model is loaded).

The adapters take an ``engine_factory`` (a zero-argument callable that loads the model). Tests
pass a factory that returns a stub, so nothing heavy is imported or downloaded.
"""

from __future__ import annotations

import threading
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEVANAGARI_NAME = "कृष्ण"  # Krishna
SPEECH_RATE = 16000


def write_wav(path: Path, seconds: float = 1.0, rate: int = SPEECH_RATE) -> Path:
    """Write a mono 16-bit WAV of ``seconds`` (0 gives a valid file with no frames)."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x10\x10" * int(seconds * rate))
    return path


def read_wav_info(path: Path) -> tuple[int, int, int, int]:
    """(channels, sample width, rate, frame count) of a WAV file."""
    with wave.open(str(path), "rb") as handle:
        return (
            handle.getnchannels(),
            handle.getsampwidth(),
            handle.getframerate(),
            handle.getnframes(),
        )


class Factory:
    """An engine factory that counts how often the model was loaded."""

    def __init__(self, engine: Any = None, *, error: Exception | None = None) -> None:
        self.engine = engine
        self.error = error
        self.calls = 0

    def __call__(self) -> Any:
        """Load the (stub) model."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.engine


class Blocker:
    """Helper for timeout tests: an engine call that blocks until released."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def wait(self) -> None:
        """Block the engine call (bounded, so a broken test cannot hang the suite)."""
        self.release.wait(timeout=5)


def leftovers(folder: Path, expected: set[str]) -> set[str]:
    """Names in ``folder`` that are not in ``expected`` (stray temp or partial files)."""
    return {item.name for item in folder.iterdir()} - expected


Callback = Callable[..., Any]
