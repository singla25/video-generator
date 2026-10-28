"""Lip sync with MuseTalk. The runtime is wired in L4; the contract is complete here."""

from __future__ import annotations

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

    def sync(self, video: Path, audio: Path, out: Path) -> None:
        """Write the lip-synced ``video`` for ``audio`` to ``out``."""
        require_audio(audio)
        with self._guard.acquire():
            model = self._model.get()
            with atomic_output(out) as tmp:
                model.run(video, audio, tmp)
