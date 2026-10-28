"""faster-whisper speech-to-text adapter contract (M2 plan AC2, G3). Model is a stub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.unit.infra.ai.support import DEVANAGARI_NAME, Blocker, Factory, write_wav
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.values import Word
from vidgen.infrastructure.ai.errors import AdapterTimeoutError, ModelLoadError
from vidgen.infrastructure.ai.faster_whisper_stt import FasterWhisperSpeechToText
from vidgen.ports import SpeechToText


@dataclass
class StubWord:
    """Shape of a faster-whisper word: text with a leading space, times, probability."""

    word: str
    start: float
    end: float
    probability: float


class StubWhisper:
    """Mimics ``WhisperModel.transcribe`` -> (segments, info)."""

    def __init__(
        self,
        words: list[StubWord] | None = None,
        *,
        error: Exception | None = None,
        blocker: Blocker | None = None,
    ) -> None:
        self.words = words or []
        self.error = error
        self.blocker = blocker
        self.kwargs: dict[str, Any] = {}

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[list[Any], Any]:
        self.kwargs = kwargs
        if self.blocker:
            self.blocker.wait()
        if self.error:
            raise self.error
        segment = SimpleNamespace(words=self.words)
        return ([segment] if self.words else []), SimpleNamespace(language="hi")


def adapter(model: StubWhisper, **kwargs: Any) -> tuple[FasterWhisperSpeechToText, Factory]:
    factory = Factory(model)
    return FasterWhisperSpeechToText(model_factory=factory, **kwargs), factory


def test_stt_adapter_returns_words_with_start_end_and_confidence(tmp_path: Path) -> None:
    """M2-S1-P1: Word list with timestamps; leading spaces from the model are stripped."""
    model = StubWhisper([StubWord(" Krishan", 1.0, 1.4, 0.93), StubWord(" ji", 1.5, 1.7, 0.8)])
    stt, _ = adapter(model)
    words = stt.transcribe(write_wav(tmp_path / "a.wav", 2))
    assert words == [Word("Krishan", 1.0, 1.4, 0.93), Word("ji", 1.5, 1.7, 0.8)]


def test_stt_adapter_satisfies_the_speech_to_text_port(tmp_path: Path) -> None:
    """M2-S1-P2: usable wherever the SpeechToText protocol is expected."""
    stt: SpeechToText = adapter(StubWhisper())[0]
    assert stt.transcribe(write_wav(tmp_path / "a.wav")) == []


def test_stt_adapter_asks_the_model_for_word_timestamps(tmp_path: Path) -> None:
    """M2-S1-P3: word_timestamps=True and the configured language reach the model."""
    model = StubWhisper([StubWord(" a", 0.0, 0.1, 0.9)])
    stt, _ = adapter(model, language="hi")
    stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert model.kwargs["word_timestamps"] is True
    assert model.kwargs["language"] == "hi"


def test_stt_adapter_loads_the_model_lazily_and_only_once(tmp_path: Path) -> None:
    """M2-S1-P4 (D-M2-3): construction loads nothing; two calls load once (kept warm)."""
    stt, factory = adapter(StubWhisper([StubWord(" a", 0.0, 0.1, 0.9)]))
    assert factory.calls == 0
    audio = write_wav(tmp_path / "a.wav")
    stt.transcribe(audio)
    stt.transcribe(audio)
    assert factory.calls == 1


def test_stt_adapter_keeps_devanagari_words_intact(tmp_path: Path) -> None:
    """M2-S1-E1."""
    stt, _ = adapter(StubWhisper([StubWord(f" {DEVANAGARI_NAME}", 0.5, 1.0, 0.7)]))
    assert stt.transcribe(write_wav(tmp_path / "a.wav"))[0].text == DEVANAGARI_NAME


def test_stt_adapter_returns_no_words_for_silence(tmp_path: Path) -> None:
    """M2-S1-E2: no speech is not an error (the slot is then marked by hand)."""
    stt, _ = adapter(StubWhisper())
    assert stt.transcribe(write_wav(tmp_path / "a.wav")) == []


def test_stt_adapter_accepts_a_zero_length_wav(tmp_path: Path) -> None:
    """M2-S1-E3: a valid WAV with no frames gives no words and no crash."""
    stt, _ = adapter(StubWhisper())
    assert stt.transcribe(write_wav(tmp_path / "z.wav", 0)) == []


def test_stt_adapter_handles_a_very_long_transcript(tmp_path: Path) -> None:
    """M2-S1-E4: 5000 words stay in order."""
    words = [StubWord(f" w{i}", i * 0.1, i * 0.1 + 0.05, 0.9) for i in range(5000)]
    stt, _ = adapter(StubWhisper(words))
    result = stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert [w.text for w in result] == [f"w{i}" for i in range(5000)]


@pytest.mark.parametrize("raw", [-0.2, 1.7])
def test_stt_adapter_clamps_confidence_into_zero_one(tmp_path: Path, raw: float) -> None:
    """M2-S1-E5: Word.confidence is always within 0..1."""
    stt, _ = adapter(StubWhisper([StubWord(" a", 0.0, 0.1, raw)]))
    assert 0.0 <= stt.transcribe(write_wav(tmp_path / "a.wav"))[0].confidence <= 1.0


def test_stt_adapter_skips_blank_words(tmp_path: Path) -> None:
    """M2-S1-E6: whitespace-only tokens are dropped."""
    stt, _ = adapter(StubWhisper([StubWord(" ", 0.0, 0.1, 0.9), StubWord(" ok", 0.2, 0.3, 0.9)]))
    assert [w.text for w in stt.transcribe(write_wav(tmp_path / "a.wav"))] == ["ok"]


def test_stt_adapter_missing_audio_file_fails_before_loading_the_model(tmp_path: Path) -> None:
    """M2-S1-N1."""
    stt, factory = adapter(StubWhisper())
    with pytest.raises(FileNotFoundError):
        stt.transcribe(tmp_path / "nope.wav")
    assert factory.calls == 0


def test_stt_adapter_empty_audio_file_is_a_coded_error(tmp_path: Path) -> None:
    """M2-S1-N2: a 0-byte file is rejected with STT_FAILED, model not called."""
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    stt, factory = adapter(StubWhisper())
    with pytest.raises(DomainError) as info:
        stt.transcribe(empty)
    assert info.value.code is FailureCode.STT_FAILED
    assert factory.calls == 0


def test_stt_adapter_model_load_failure_is_a_model_load_error(tmp_path: Path) -> None:
    """M2-S1-N3: custom exception with code STT_FAILED, original error chained."""
    factory = Factory(error=OSError("weights missing"))
    stt = FasterWhisperSpeechToText(model_factory=factory)
    with pytest.raises(ModelLoadError) as info:
        stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert info.value.code is FailureCode.STT_FAILED
    assert isinstance(info.value.__cause__, OSError)


def test_stt_adapter_model_crash_during_transcribe_is_stt_failed(tmp_path: Path) -> None:
    """M2-S1-N4."""
    stt, _ = adapter(StubWhisper(error=RuntimeError("mps out of memory")))
    with pytest.raises(DomainError) as info:
        stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert info.value.code is FailureCode.STT_FAILED


def test_stt_adapter_times_out_instead_of_hanging(tmp_path: Path) -> None:
    """M2-S1-E7: a stuck model raises AdapterTimeoutError (RENDER_TIMEOUT, retryable)."""
    blocker = Blocker()
    stt, _ = adapter(StubWhisper([StubWord(" a", 0, 0.1, 0.9)], blocker=blocker), timeout_s=0.1)
    try:
        with pytest.raises(AdapterTimeoutError) as info:
            stt.transcribe(write_wav(tmp_path / "a.wav"))
        assert info.value.code is FailureCode.RENDER_TIMEOUT
    finally:
        blocker.release.set()
