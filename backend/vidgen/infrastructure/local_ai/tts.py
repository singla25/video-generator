"""Voice cloning with Chatterbox-Multilingual (MIT)."""

from __future__ import annotations

import array
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vidgen.infrastructure.local_ai._common import (
    LazyModel,
    Loader,
    atomic_output,
    require_audio,
)
from vidgen.infrastructure.local_ai.loaders import load_chatterbox

PCM_MAX = 32767


def _to_pcm16(samples: Sequence[float]) -> array.array[int]:
    """Convert int samples as-is, or float samples in [-1, 1] to 16-bit PCM."""
    if samples and isinstance(samples[0], float):
        return array.array("h", (max(-PCM_MAX, min(PCM_MAX, int(s * PCM_MAX))) for s in samples))
    return array.array("h", (int(s) for s in samples))


class ChatterboxVoiceCloner:
    """``VoiceCloner`` port backed by a lazily loaded Chatterbox model."""

    def __init__(self, weights_dir: Path, loader: Loader[Any] = load_chatterbox) -> None:
        self._model = LazyModel("voice cloning", weights_dir, loader)

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        """Write the cloned speech to ``out`` (WAV) and return its duration in seconds."""
        if not text.strip():
            raise ValueError("text to speak must not be blank")
        require_audio(voice_sample)
        samples, rate = self._model.get().generate(text.strip(), voice_sample)
        pcm = _to_pcm16(samples)
        with atomic_output(out) as tmp, wave.open(str(tmp), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(pcm.tobytes())
        return float(len(pcm) / rate)
