"""Shared helpers for the adapters: lazy single model load, audio checks, atomic outputs."""

from __future__ import annotations

import gc
import os
import sys
import threading
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Generic, TypeVar

from vidgen.infrastructure.local_ai.errors import EmptyAudioError, ModelWeightsMissingError
from vidgen.infrastructure.local_ai.offline import offline_only

M = TypeVar("M")
Loader = Callable[[Path], M]


class LazyModel(Generic[M]):
    """Loads a model on first use (weights checked then, not at construction), exactly once."""

    def __init__(self, label: str, weights_dir: Path, loader: Loader[M]) -> None:
        self._label = label
        self._weights_dir = weights_dir
        self._loader = loader
        self._model: M | None = None
        self._lock = threading.Lock()

    def get(self) -> M:
        """Return the loaded model, loading it on the first call."""
        with self._lock:
            if self._model is None:
                self._check_weights()
                with offline_only():
                    self._model = self._loader(self._weights_dir)
            return self._model

    def release(self) -> None:
        """Drop the loaded model and give its memory back (the next ``get`` reloads it).

        Lets a caller run the models one stage at a time on a machine too small to hold all four.
        """
        with self._lock:
            self._model = None
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.backends.mps.is_available():
            torch.mps.empty_cache()

    def _check_weights(self) -> None:
        folder = self._weights_dir
        if not folder.is_dir() or not any(folder.iterdir()):
            raise ModelWeightsMissingError(
                f"{self._label} weights not found in folder '{folder}'; "
                "download them into the local AI weights folder first"
            )


def require_audio(path: Path) -> None:
    """Raise ``FileNotFoundError`` for a missing file and ``EmptyAudioError`` for zero samples."""
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path.name}")
    if path.stat().st_size == 0:
        raise EmptyAudioError(f"audio file is empty: {path.name}")
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
    except (wave.Error, EOFError):
        return  # not a WAV (e.g. mp3): the model decides
    if frames == 0:
        raise EmptyAudioError(f"audio file has no samples: {path.name}")


@contextmanager
def atomic_output(out: Path) -> Iterator[Path]:
    """Yield a temp path next to ``out``; publish it on success, delete it on any failure."""
    tmp = out.with_name(f".{out.stem}.{os.getpid()}.part{out.suffix}")
    try:
        yield tmp
        os.replace(tmp, out)
    finally:
        with suppress(FileNotFoundError):
            tmp.unlink()
