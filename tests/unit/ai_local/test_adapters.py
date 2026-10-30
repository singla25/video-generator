"""AC3, AC5, AC7, AC8: real adapters honour the ports, tested with stubbed models only."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import pytest

from tests.unit.ai_local.conftest import make_settings, write_wav
from vidgen.infrastructure.local_ai.errors import (
    AiBusyError,
    EmptyAudioError,
    ModelWeightsMissingError,
)
from vidgen.infrastructure.local_ai.guard import SingleRenderGuard
from vidgen.infrastructure.local_ai.lipsync import MuseTalkLipSyncer
from vidgen.infrastructure.local_ai.offline import offline_only
from vidgen.infrastructure.local_ai.stt import FasterWhisperSpeechToText
from vidgen.infrastructure.local_ai.transliterate import QwenTransliterator
from vidgen.infrastructure.local_ai.tts import ChatterboxVoiceCloner

SAMPLE_RATE = 24000


# ---- stub models (the "loader" is the seam where torch would be imported) --------------


class StubWord:
    """Shape of a faster-whisper word."""

    def __init__(self, word: str, start: float, end: float, probability: float) -> None:
        self.word, self.start, self.end, self.probability = word, start, end, probability


class StubSegment:
    """Shape of a faster-whisper segment."""

    def __init__(self, words: list[StubWord]) -> None:
        self.words = words


class StubWhisper:
    """``transcribe(path) -> (segments, info)`` like faster-whisper's model."""

    def __init__(self, words: list[StubWord]) -> None:
        self._words = words
        self.calls: list[str] = []

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[list[StubSegment], object]:
        self.calls.append(audio)
        return [StubSegment(self._words)], object()


class Loader:
    """``loader(weights_dir) -> model``; records every load."""

    def __init__(self, model: Any) -> None:
        self.model = model
        self.loaded_from: list[Path] = []

    def __call__(self, weights: Path) -> Any:
        self.loaded_from.append(weights)
        return self.model


# ---- SpeechToText -----------------------------------------------------------------------


def test_stt_returns_words_with_times_and_confidence(weights_dir: Path, tmp_path: Path) -> None:
    model = StubWhisper([StubWord(" Krishan", 0.0, 0.8, 0.93), StubWord(" ji", 0.8, 1.0, 0.8)])
    stt = FasterWhisperSpeechToText(weights_dir, loader=Loader(model))
    words = stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert [(x.text, x.start_s, x.end_s, x.confidence) for x in words] == [
        ("Krishan", 0.0, 0.8, 0.93),
        ("ji", 0.8, 1.0, 0.8),
    ]


def test_stt_loads_the_model_lazily_and_once(weights_dir: Path, tmp_path: Path) -> None:
    loader = Loader(StubWhisper([]))
    stt = FasterWhisperSpeechToText(weights_dir, loader=loader)
    assert loader.loaded_from == []
    audio = write_wav(tmp_path / "a.wav")
    stt.transcribe(audio)
    stt.transcribe(audio)
    assert loader.loaded_from == [weights_dir]


def test_stt_missing_weights_raise_a_custom_error_naming_the_folder(
    missing_weights: Path, tmp_path: Path
) -> None:
    stt = FasterWhisperSpeechToText(missing_weights, loader=Loader(StubWhisper([])))
    with pytest.raises(ModelWeightsMissingError) as caught:
        stt.transcribe(write_wav(tmp_path / "a.wav"))
    assert missing_weights.name in str(caught.value)


def test_stt_empty_audio_is_a_clear_error_and_never_reaches_the_model(
    weights_dir: Path, tmp_path: Path
) -> None:
    model = StubWhisper([])
    stt = FasterWhisperSpeechToText(weights_dir, loader=Loader(model))
    with pytest.raises(EmptyAudioError):
        stt.transcribe(write_wav(tmp_path / "empty.wav", seconds=0))
    assert model.calls == []


def test_stt_silence_with_no_words_returns_an_empty_list(weights_dir: Path, tmp_path: Path) -> None:
    stt = FasterWhisperSpeechToText(weights_dir, loader=Loader(StubWhisper([])))
    assert stt.transcribe(write_wav(tmp_path / "quiet.wav")) == []


def test_stt_missing_audio_file_is_a_file_error_not_a_model_error(
    weights_dir: Path, tmp_path: Path
) -> None:
    stt = FasterWhisperSpeechToText(weights_dir, loader=Loader(StubWhisper([])))
    with pytest.raises(FileNotFoundError):
        stt.transcribe(tmp_path / "nope.wav")


# ---- Transliterator ---------------------------------------------------------------------


class StubLlm:
    """``generate(prompt) -> text``; records prompts."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        """Return the canned reply."""
        self.prompts.append(prompt)
        return self.reply


def transliterator(weights: Path, llm: StubLlm) -> QwenTransliterator:
    """An adapter around a stub LLM."""
    return QwenTransliterator(weights, loader=Loader(llm))


def test_transliterator_returns_the_cleaned_model_answer(weights_dir: Path) -> None:
    llm = StubLlm("  कृष्ण \n")
    assert transliterator(weights_dir, llm).transliterate("Krishan", "Devanagari") == "कृष्ण"
    assert "Krishan" in llm.prompts[0]


@pytest.mark.parametrize("name", ["A", "ए", "Ng"])
def test_transliterator_accepts_one_character_names(weights_dir: Path, name: str) -> None:
    assert transliterator(weights_dir, StubLlm("अ")).transliterate(name, "Devanagari") == "अ"


def test_hindi_input_survives_the_prompt_unchanged(weights_dir: Path) -> None:
    llm = StubLlm("Krishan")
    transliterator(weights_dir, llm).transliterate("कृष्ण", "Latin")
    assert "कृष्ण" in llm.prompts[0]


def test_transliterator_blank_text_returns_empty_without_calling_the_model(
    weights_dir: Path,
) -> None:
    llm = StubLlm("x")
    assert transliterator(weights_dir, llm).transliterate("  ", "Devanagari") == ""
    assert llm.prompts == []


def test_transliterator_keeps_only_the_first_line_of_a_chatty_answer(weights_dir: Path) -> None:
    llm = StubLlm("कृष्ण\nHere is the transliteration you asked for.")
    assert transliterator(weights_dir, llm).transliterate("Krishan", "Devanagari") == "कृष्ण"


def test_transliterator_missing_weights_raise_custom_error(missing_weights: Path) -> None:
    with pytest.raises(ModelWeightsMissingError):
        transliterator(missing_weights, StubLlm("x")).transliterate("A", "Devanagari")


# ---- VoiceCloner ------------------------------------------------------------------------


class StubTts:
    """``generate(text, voice_sample) -> (samples, rate)``; can fail for one text."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.texts: list[str] = []

    def generate(self, text: str, voice_sample: Path) -> tuple[list[int], int]:
        """One second of a square-ish wave, or an error for ``fail_on``."""
        self.texts.append(text)
        if text == self.fail_on:
            raise RuntimeError("model blew up")
        return [100, -100] * (SAMPLE_RATE // 2), SAMPLE_RATE


def test_voice_cloner_writes_a_wav_and_returns_its_duration(
    weights_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "name.wav"
    cloner = ChatterboxVoiceCloner(weights_dir, loader=Loader(StubTts()))
    seconds = cloner.synthesize("कृष्ण", write_wav(tmp_path / "ref.wav"), out)
    assert seconds == pytest.approx(1.0)
    with wave.open(str(out), "rb") as handle:
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() / handle.getframerate() == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["A", "ए", "कृष्ण कुमार", "Zoë"])
def test_voice_cloner_handles_short_hindi_and_accented_text(
    weights_dir: Path, tmp_path: Path, text: str
) -> None:
    out = tmp_path / "n.wav"
    cloner = ChatterboxVoiceCloner(weights_dir, loader=Loader(StubTts()))
    assert cloner.synthesize(text, write_wav(tmp_path / "ref.wav"), out) > 0
    assert out.exists()


def test_voice_cloner_rejects_blank_text_before_the_model(
    weights_dir: Path, tmp_path: Path
) -> None:
    model = StubTts()
    cloner = ChatterboxVoiceCloner(weights_dir, loader=Loader(model))
    with pytest.raises(ValueError):
        cloner.synthesize("  ", write_wav(tmp_path / "ref.wav"), tmp_path / "o.wav")
    assert model.texts == []


def test_voice_cloner_empty_voice_sample_is_a_clear_error(
    weights_dir: Path, tmp_path: Path
) -> None:
    cloner = ChatterboxVoiceCloner(weights_dir, loader=Loader(StubTts()))
    with pytest.raises(EmptyAudioError):
        cloner.synthesize("A", write_wav(tmp_path / "ref.wav", seconds=0), tmp_path / "o.wav")


def test_voice_cloner_missing_weights_raise_custom_error(
    missing_weights: Path, tmp_path: Path
) -> None:
    cloner = ChatterboxVoiceCloner(missing_weights, loader=Loader(StubTts()))
    with pytest.raises(ModelWeightsMissingError):
        cloner.synthesize("A", write_wav(tmp_path / "ref.wav"), tmp_path / "o.wav")


def test_voice_cloner_failure_leaves_no_partial_output_file(
    weights_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "o.wav"
    cloner = ChatterboxVoiceCloner(weights_dir, loader=Loader(StubTts(fail_on="bad")))
    with pytest.raises(Exception):  # noqa: B017 - any typed failure; the point is no file left
        cloner.synthesize("bad", write_wav(tmp_path / "ref.wav"), out)
    assert not out.exists()


def test_one_failing_row_does_not_poison_the_adapter_for_the_next_row(
    weights_dir: Path, tmp_path: Path
) -> None:
    """AC7: row isolation at adapter level; the same loaded model serves the next row."""
    loader = Loader(StubTts(fail_on="bad"))
    cloner = ChatterboxVoiceCloner(weights_dir, loader=loader)
    ref = write_wav(tmp_path / "ref.wav")
    with pytest.raises(Exception):  # noqa: B017
        cloner.synthesize("bad", ref, tmp_path / "1.wav")
    assert cloner.synthesize("good", ref, tmp_path / "2.wav") > 0
    assert len(loader.loaded_from) == 1


# ---- LipSyncer --------------------------------------------------------------------------


class StubMuseTalk:
    """``run(video, audio, out)`` writes bytes to ``out`` (and may then fail)."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.runs: list[tuple[Path, Path, Path]] = []

    def run(self, video: Path, audio: Path, out: Path) -> None:
        """Write a partial file, then fail if asked to."""
        self.runs.append((video, audio, out))
        out.write_bytes(b"partial")
        if self.fail:
            raise RuntimeError("no face found")


def video_file(tmp_path: Path) -> Path:
    """A placeholder input video (the stub never decodes it)."""
    path = tmp_path / "in.mp4"
    path.write_bytes(b"v")
    return path


def test_lipsync_writes_the_output_through_the_model(weights_dir: Path, tmp_path: Path) -> None:
    video, out, model = video_file(tmp_path), tmp_path / "out.mp4", StubMuseTalk()
    MuseTalkLipSyncer(weights_dir, loader=Loader(model)).sync(
        video, write_wav(tmp_path / "a.wav"), out
    )
    assert out.exists()
    assert model.runs[0][0] == video


def test_lipsync_failure_leaves_no_partial_video(weights_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(StubMuseTalk(fail=True)))
    with pytest.raises(Exception):  # noqa: B017
        syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), out)
    assert not out.exists()


def test_lipsync_empty_audio_is_a_clear_error(weights_dir: Path, tmp_path: Path) -> None:
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(StubMuseTalk()))
    with pytest.raises(EmptyAudioError):
        syncer.sync(
            video_file(tmp_path), write_wav(tmp_path / "a.wav", seconds=0), tmp_path / "o.mp4"
        )


def test_lipsync_missing_weights_raise_custom_error(missing_weights: Path, tmp_path: Path) -> None:
    syncer = MuseTalkLipSyncer(missing_weights, loader=Loader(StubMuseTalk()))
    with pytest.raises(ModelWeightsMissingError):
        syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), tmp_path / "o.mp4")


def test_lipsync_runs_inside_the_single_render_guard(weights_dir: Path, tmp_path: Path) -> None:
    """AC7: a second concurrent MuseTalk run is refused rather than exhausting memory."""
    guard = SingleRenderGuard()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(StubMuseTalk()), guard=guard)
    with guard.acquire(), pytest.raises(AiBusyError):
        syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), tmp_path / "o.mp4")


# ---- no network at run time -------------------------------------------------------------


def test_adapters_run_with_the_network_blocked(weights_dir: Path, tmp_path: Path) -> None:
    """AC8: a stubbed pass makes no socket calls."""
    stt = FasterWhisperSpeechToText(weights_dir, loader=Loader(StubWhisper([])))
    with offline_only():
        assert stt.transcribe(write_wav(tmp_path / "a.wav")) == []


# ---- real-model smoke (skipped by default) ----------------------------------------------


@pytest.mark.local_ai
def test_real_whisper_runs_on_a_synthetic_clip(tmp_path: Path) -> None:
    from vidgen.infrastructure.local_ai.factory import build_ai_adapters

    adapters = build_ai_adapters(make_settings(tmp_path, ai_mode="local"))
    assert adapters.stt.transcribe(write_wav(tmp_path / "a.wav", seconds=1)) is not None
