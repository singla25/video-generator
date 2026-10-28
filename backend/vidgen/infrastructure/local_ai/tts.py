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
WINDOW_S = 0.02  # analysis window for the speech/silence decision
ACTIVE_SHARE = 0.10  # a window is speech when its level is >= 10 % of the loudest window
END_GAP_S = 0.35  # a silence this long ends the utterance
EDGE_MARGIN_S = 0.03  # kept around the speech so consonants are not clipped


def _to_pcm16(samples: Sequence[float]) -> array.array[int]:
    """Convert int samples as-is, or float samples in [-1, 1] to 16-bit PCM."""
    if samples and isinstance(samples[0], float):
        return array.array("h", (max(-PCM_MAX, min(PCM_MAX, int(s * PCM_MAX))) for s in samples))
    return array.array("h", (int(s) for s in samples))


def _window_levels(pcm: array.array[int], size: int) -> list[float]:
    """Mean absolute level of each consecutive window of ``size`` samples."""
    return [
        sum(abs(v) for v in pcm[i : i + size]) / len(pcm[i : i + size])
        for i in range(0, len(pcm), size)
    ]


def trim_to_first_utterance(pcm: array.array[int], rate: int) -> array.array[int]:
    """Cut leading silence and everything after the first utterance.

    Chatterbox sometimes keeps babbling quietly after a short text (a name), which would make the
    clip far longer than its slot. Silent input is returned unchanged.
    """
    size = max(1, int(rate * WINDOW_S))
    levels = _window_levels(pcm, size)
    peak = max(levels, default=0.0)
    if peak <= 0:
        return pcm
    active = [level >= peak * ACTIVE_SHARE for level in levels]
    first = active.index(True)
    gap_windows = max(1, round(END_GAP_S / WINDOW_S))
    last, quiet = first, 0
    for index in range(first, len(active)):
        if active[index]:
            last, quiet = index, 0
        else:
            quiet += 1
            if quiet >= gap_windows:
                break
    margin = int(rate * EDGE_MARGIN_S)
    return pcm[max(0, first * size - margin) : min(len(pcm), (last + 1) * size + margin)]


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
        pcm = trim_to_first_utterance(_to_pcm16(samples), rate)
        with atomic_output(out) as tmp, wave.open(str(tmp), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(pcm.tobytes())
        return float(len(pcm) / rate)

    def release(self) -> None:
        """Unload the model to free memory; it loads again on the next use."""
        self._model.release()
