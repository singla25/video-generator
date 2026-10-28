"""Chatterbox voice-cloner contract (M2 plan AC3, AC7). The model is a stub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.unit.infra.ai.support import (
    DEVANAGARI_NAME,
    Blocker,
    Factory,
    leftovers,
    read_wav_info,
    write_wav,
)
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ai.chatterbox_cloner import ChatterboxVoiceCloner
from vidgen.infrastructure.ai.errors import AdapterTimeoutError, ModelLoadError
from vidgen.ports import VoiceCloner

RATE = 24000


class StubTts:
    """``synthesize(text, voice_sample, language) -> (float samples in -1..1, sample rate)``."""

    def __init__(
        self,
        samples: list[float] | None = None,
        rate: int = RATE,
        error: Exception | None = None,
        blocker: Blocker | None = None,
    ) -> None:
        self.samples = [0.1] * RATE if samples is None else samples
        self.rate, self.error, self.blocker = rate, error, blocker
        self.calls: list[tuple[str, Path, str]] = []

    def synthesize(self, text: str, voice_sample: Path, language: str) -> tuple[list[float], int]:
        self.calls.append((text, voice_sample, language))
        if self.blocker:
            self.blocker.wait()
        if self.error:
            raise self.error
        return self.samples, self.rate


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "ref.wav", 3)


def make(engine: StubTts, **kwargs: Any) -> tuple[ChatterboxVoiceCloner, Factory]:
    factory = Factory(engine)
    return ChatterboxVoiceCloner(engine_factory=factory, **kwargs), factory


def test_cloner_writes_out_and_returns_the_duration(tmp_path: Path, sample: Path) -> None:
    """M2-S3-P1: 1.5 s of audio -> out is a mono 16-bit WAV, return value 1.5."""
    engine = StubTts([0.2] * int(1.5 * RATE))
    cloner, _ = make(engine)
    out = tmp_path / "voice.wav"
    seconds = cloner.synthesize("Krishan", sample, out)
    channels, width, rate, frames = read_wav_info(out)
    assert (channels, width, rate) == (1, 2, RATE)
    assert seconds == pytest.approx(1.5)
    assert frames / rate == pytest.approx(seconds)


def test_cloner_satisfies_the_voice_cloner_port(tmp_path: Path, sample: Path) -> None:
    """M2-S3-P2."""
    cloner: VoiceCloner = make(StubTts())[0]
    assert cloner.synthesize("x", sample, tmp_path / "o.wav") > 0


def test_cloner_passes_text_reference_and_hindi_language_to_the_model(
    tmp_path: Path, sample: Path
) -> None:
    """M2-S3-P3."""
    engine = StubTts()
    make(engine, language="hi")[0].synthesize(DEVANAGARI_NAME, sample, tmp_path / "o.wav")
    assert engine.calls == [(DEVANAGARI_NAME, sample, "hi")]


def test_cloner_loads_the_model_lazily_and_once(tmp_path: Path, sample: Path) -> None:
    """M2-S3-P4 (D-M2-3)."""
    cloner, factory = make(StubTts())
    assert factory.calls == 0
    cloner.synthesize("a", sample, tmp_path / "1.wav")
    cloner.synthesize("b", sample, tmp_path / "2.wav")
    assert factory.calls == 1


def test_cloner_clips_samples_outside_minus_one_to_one(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E1: 1.5 becomes full scale, not a wrapped-around click."""
    cloner, _ = make(StubTts([1.5, -1.5, 0.0]))
    out = tmp_path / "o.wav"
    cloner.synthesize("a", sample, out)
    import array
    import wave

    with wave.open(str(out), "rb") as handle:
        values = array.array("h", handle.readframes(3))
    assert values[0] == 32767
    assert values[1] <= -32767
    assert values[2] == 0


def test_cloner_overwrites_a_stale_out_file_on_success(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E2: retry-safe: a leftover from a crashed attempt is replaced."""
    out = tmp_path / "o.wav"
    out.write_bytes(b"stale")
    make(StubTts())[0].synthesize("a", sample, out)
    assert read_wav_info(out)[3] == RATE


def test_cloner_leaves_no_stray_temp_files_on_success(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E3."""
    make(StubTts())[0].synthesize("a", sample, tmp_path / "o.wav")
    assert leftovers(tmp_path, {"ref.wav", "o.wav"}) == set()


def test_cloner_missing_voice_sample_fails_without_output(tmp_path: Path) -> None:
    """M2-S3-N1."""
    engine = StubTts()
    cloner, factory = make(engine)
    with pytest.raises(FileNotFoundError):
        cloner.synthesize("a", tmp_path / "nope.wav", tmp_path / "o.wav")
    assert factory.calls == 0
    assert not (tmp_path / "o.wav").exists()


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_cloner_empty_text_is_tts_failed_and_writes_nothing(
    tmp_path: Path, sample: Path, text: str
) -> None:
    """M2-S3-N2."""
    engine = StubTts()
    with pytest.raises(DomainError) as info:
        make(engine)[0].synthesize(text, sample, tmp_path / "o.wav")
    assert info.value.code is FailureCode.TTS_FAILED
    assert engine.calls == []
    assert not (tmp_path / "o.wav").exists()


def test_cloner_zero_length_model_output_is_tts_failed_and_writes_nothing(
    tmp_path: Path, sample: Path
) -> None:
    """M2-S3-E4: the model returned no samples."""
    with pytest.raises(DomainError) as info:
        make(StubTts([]))[0].synthesize("a", sample, tmp_path / "o.wav")
    assert info.value.code is FailureCode.TTS_FAILED
    assert not (tmp_path / "o.wav").exists()


def test_cloner_model_crash_is_tts_failed_with_no_partial_file(
    tmp_path: Path, sample: Path
) -> None:
    """M2-S3-N3."""
    with pytest.raises(DomainError) as info:
        make(StubTts(error=RuntimeError("mps oom")))[0].synthesize("a", sample, tmp_path / "o.wav")
    assert info.value.code is FailureCode.TTS_FAILED
    assert leftovers(tmp_path, {"ref.wav"}) == set()


def test_cloner_model_load_failure_is_a_model_load_error(tmp_path: Path, sample: Path) -> None:
    """M2-S3-N4."""
    cloner = ChatterboxVoiceCloner(engine_factory=Factory(error=OSError("no weights")))
    with pytest.raises(ModelLoadError) as info:
        cloner.synthesize("a", sample, tmp_path / "o.wav")
    assert info.value.code is FailureCode.TTS_FAILED
    assert not (tmp_path / "o.wav").exists()


def test_cloner_rejects_text_over_the_limit_without_calling_the_model(
    tmp_path: Path, sample: Path
) -> None:
    """M2-S3-E5: very long text -> NAME_TOO_LONG_TO_SPEAK."""
    engine = StubTts()
    cloner, _ = make(engine, max_chars=100)
    with pytest.raises(DomainError) as info:
        cloner.synthesize("a" * 101, sample, tmp_path / "o.wav")
    assert info.value.code is FailureCode.NAME_TOO_LONG_TO_SPEAK
    assert engine.calls == []


def test_cloner_accepts_text_exactly_at_the_limit(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E6."""
    cloner, _ = make(StubTts(), max_chars=100)
    assert cloner.synthesize("a" * 100, sample, tmp_path / "o.wav") > 0


def test_cloner_timeout_raises_and_leaves_no_output(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E7."""
    blocker = Blocker()
    cloner, _ = make(StubTts(blocker=blocker), timeout_s=0.1)
    try:
        with pytest.raises(AdapterTimeoutError) as info:
            cloner.synthesize("a", sample, tmp_path / "o.wav")
        assert info.value.code is FailureCode.RENDER_TIMEOUT
    finally:
        blocker.release.set()
    assert not (tmp_path / "o.wav").exists()


def test_cloner_unwritable_output_folder_is_storage_error(tmp_path: Path, sample: Path) -> None:
    """M2-S3-E8: out in a folder that does not exist -> STORAGE_ERROR, no crash."""
    with pytest.raises(DomainError) as info:
        make(StubTts())[0].synthesize("a", sample, tmp_path / "missing-dir" / "o.wav")
    assert info.value.code is FailureCode.STORAGE_ERROR
