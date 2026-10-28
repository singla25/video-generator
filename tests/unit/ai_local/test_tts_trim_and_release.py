"""First-utterance trimming of cloned speech, and model release on every adapter (L6c)."""

from __future__ import annotations

import array
import sys
import types
import wave
from pathlib import Path
from typing import Any

import pytest

from tests.unit.ai_local.conftest import write_wav
from vidgen.infrastructure.local_ai._common import LazyModel
from vidgen.infrastructure.local_ai.lipsync import MuseTalkLipSyncer
from vidgen.infrastructure.local_ai.stt import FasterWhisperSpeechToText
from vidgen.infrastructure.local_ai.transliterate import QwenTransliterator
from vidgen.infrastructure.local_ai.tts import ChatterboxVoiceCloner, trim_to_first_utterance

RATE = 16000


def tone(seconds: float, level: int) -> list[int]:
    """Alternating +/- ``level`` samples (a constant-level signal)."""
    return [level if i % 2 else -level for i in range(int(seconds * RATE))]


def silence(seconds: float) -> list[int]:
    """Digital silence."""
    return [0] * int(seconds * RATE)


def seconds_of(samples: Any) -> float:
    """Duration of a sample sequence."""
    return len(samples) / RATE


class Tts:
    """Chatterbox stand-in returning fixed samples."""

    def __init__(self, samples: list[int]) -> None:
        self.samples = samples

    def generate(self, text: str, voice_sample: Path) -> tuple[list[int], int]:
        """Return the canned audio."""
        return self.samples, RATE


def synth(weights: Path, tmp_path: Path, samples: list[int]) -> tuple[float, Path]:
    """Run the cloner on canned audio; return (duration, output path)."""
    out = tmp_path / "name.wav"
    cloner = ChatterboxVoiceCloner(weights, loader=lambda _: Tts(samples))
    return cloner.synthesize("A", write_wav(tmp_path / "ref.wav"), out), out


# ---- trimming ---------------------------------------------------------------------------


def test_babble_after_the_name_is_cut_off(weights_dir: Path, tmp_path: Path) -> None:
    name = tone(0.4, 8000)
    audio = name + silence(0.5) + tone(1.5, 2500)  # quiet babble after a long pause
    seconds, out = synth(weights_dir, tmp_path, audio)
    assert seconds == pytest.approx(0.4, abs=0.1)
    with wave.open(str(out), "rb") as handle:
        assert handle.getnframes() / RATE == pytest.approx(seconds)


def test_leading_silence_is_removed(weights_dir: Path, tmp_path: Path) -> None:
    seconds, _ = synth(weights_dir, tmp_path, silence(0.6) + tone(0.4, 8000))
    assert seconds == pytest.approx(0.4, abs=0.1)


def test_a_short_pause_inside_the_name_is_kept() -> None:
    audio = array.array("h", tone(0.3, 8000) + silence(0.1) + tone(0.3, 8000))
    assert seconds_of(trim_to_first_utterance(audio, RATE)) == pytest.approx(0.7, abs=0.1)


def test_a_single_utterance_is_kept_whole() -> None:
    audio = array.array("h", tone(0.5, 8000))
    assert seconds_of(trim_to_first_utterance(audio, RATE)) == pytest.approx(0.5, abs=0.1)


def test_silence_only_is_returned_unchanged() -> None:
    audio = array.array("h", silence(0.5))
    assert trim_to_first_utterance(audio, RATE) == audio


def test_empty_samples_are_returned_unchanged() -> None:
    assert len(trim_to_first_utterance(array.array("h"), RATE)) == 0


def test_float_samples_are_converted_then_trimmed(weights_dir: Path, tmp_path: Path) -> None:
    audio = [0.5 if i % 2 else -0.5 for i in range(int(0.4 * RATE))] + [0.0] * int(1.0 * RATE)
    seconds, _ = synth(weights_dir, tmp_path, audio)  # type: ignore[arg-type]
    assert seconds == pytest.approx(0.4, abs=0.1)


def test_trimmed_clip_never_exceeds_the_generated_audio() -> None:
    audio = array.array("h", tone(0.05, 8000))
    assert len(trim_to_first_utterance(audio, RATE)) <= len(audio)


def test_trimming_makes_a_name_fit_a_short_slot(weights_dir: Path, tmp_path: Path) -> None:
    """The whole point: babble must not make the clip longer than its slot."""
    audio = tone(0.5, 8000) + silence(0.6) + tone(3.0, 3000)
    seconds, _ = synth(weights_dir, tmp_path, audio)
    assert seconds < 1.0


# ---- release ----------------------------------------------------------------------------


class Counting:
    """A loader that counts loads and hands out distinct models."""

    def __init__(self) -> None:
        self.loads = 0

    def __call__(self, weights: Path) -> Any:
        self.loads += 1
        return types.SimpleNamespace(n=self.loads)


def test_release_before_load_is_safe(weights_dir: Path) -> None:
    lazy: LazyModel[Any] = LazyModel("x", weights_dir, Counting())
    lazy.release()
    lazy.release()  # idempotent


def test_release_drops_the_model_and_the_next_get_reloads(weights_dir: Path) -> None:
    loader = Counting()
    lazy: LazyModel[Any] = LazyModel("x", weights_dir, loader)
    first = lazy.get()
    assert lazy.get() is first and loader.loads == 1
    lazy.release()
    second = lazy.get()
    assert second is not first
    assert loader.loads == 2


def test_release_actually_frees_the_reference(weights_dir: Path) -> None:
    import weakref

    class Model:
        pass

    lazy: LazyModel[Any] = LazyModel("x", weights_dir, lambda _: Model())
    ref = weakref.ref(lazy.get())
    lazy.release()
    assert ref() is None


def test_release_empties_the_mps_cache_when_torch_is_loaded(
    weights_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleared: list[int] = []
    fake = types.SimpleNamespace(
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True)),
        mps=types.SimpleNamespace(empty_cache=lambda: cleared.append(1)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    LazyModel("x", weights_dir, Counting()).release()
    assert cleared == [1]


def test_release_without_torch_does_not_import_it(
    weights_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    LazyModel("x", weights_dir, Counting()).release()
    assert "torch" not in sys.modules


def test_release_skips_the_cache_when_mps_is_unavailable(
    weights_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleared: list[int] = []
    fake = types.SimpleNamespace(
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
        mps=types.SimpleNamespace(empty_cache=lambda: cleared.append(1)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    LazyModel("x", weights_dir, Counting()).release()
    assert cleared == []


def adapters(weights: Path, loader: Counting) -> list[Any]:
    """All four adapters wired to one counting loader."""
    return [
        FasterWhisperSpeechToText(weights, loader=loader),
        QwenTransliterator(weights, loader=loader),
        ChatterboxVoiceCloner(weights, loader=loader),
        MuseTalkLipSyncer(weights, loader=loader),
    ]


def test_every_adapter_has_a_safe_idempotent_release(weights_dir: Path) -> None:
    for adapter in adapters(weights_dir, Counting()):
        adapter.release()
        adapter.release()


def test_adapter_reloads_its_model_after_release(weights_dir: Path, tmp_path: Path) -> None:
    class Whisper:
        def transcribe(self, audio: str, **k: Any) -> tuple[list[Any], object]:
            return [], object()

    loads: list[Path] = []

    def loader(weights: Path) -> Whisper:
        loads.append(weights)
        return Whisper()

    stt = FasterWhisperSpeechToText(weights_dir, loader=loader)
    audio = write_wav(tmp_path / "a.wav")
    stt.transcribe(audio)
    stt.release()
    stt.transcribe(audio)
    assert len(loads) == 2
