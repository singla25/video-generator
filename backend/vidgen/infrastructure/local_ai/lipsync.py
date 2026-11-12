"""Lip sync with MuseTalk v1.5 (Apple silicon, MPS).

One render at a time: a run peaks at 16-18 GB of the 24 GB (M2 spike), so ``SingleRenderGuard``
refuses a second one. The models load on the first call and stay loaded; face boxes are cached
per template. Set up with ``backend/scripts/setup_musetalk.py``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from vidgen.infrastructure.local_ai._common import (
    LazyModel,
    Loader,
    atomic_output,
    require_audio,
)
from vidgen.infrastructure.local_ai.guard import SingleRenderGuard
from vidgen.infrastructure.local_ai.loaders import load_musetalk


def _check_start(start_s: float) -> None:
    """Reject a start that cannot be a position in a video, before any model or file work."""
    if not math.isfinite(start_s) or start_s < 0:
        raise ValueError(f"start_s must be a finite number of seconds >= 0, got {start_s!r}")


class MuseTalkLipSyncer:
    """``LipSyncer`` port: one MuseTalk run at a time, no partial video on failure."""

    def __init__(
        self,
        weights_dir: Path,
        loader: Loader[Any] = load_musetalk,
        guard: SingleRenderGuard | None = None,
    ) -> None:
        self._model = LazyModel("lip sync", weights_dir, loader)
        self._guard = guard or SingleRenderGuard()

    def sync(
        self,
        video: Path,
        audio: Path,
        out: Path,
        start_s: float = 0.0,
        key_from: Path | None = None,
    ) -> None:
        """Write ``video`` lip-synced to ``audio`` from ``start_s`` on to ``out``.

        ``key_from`` is the video whose face boxes are reused (DD-40); ``None`` uses ``video``.
        """
        _check_start(start_s)
        require_audio(audio)
        with self._guard.acquire():
            model = self._model.get()
            with atomic_output(out) as tmp:
                model.run(video, audio, tmp, start_s, key_from)

    def warm_up(self) -> None:
        """Load the model now (no inference), so missing weights show at start-up."""
        self._model.get()

    def release(self) -> None:
        """Unload the model to free memory; it loads again on the next use."""
        self._model.release()
