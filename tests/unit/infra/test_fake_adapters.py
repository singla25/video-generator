"""Deterministic fake AI adapters used while ai_backend=fake (ADR-008)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from vidgen.domain.values import Word
from vidgen.infrastructure.fakes import (
    FakeLipSyncer,
    FakeQualityChecker,
    FakeSpeechToText,
    FakeVoiceCloner,
)

SAMPLE = Path("unused-voice-sample.wav")
DEVANAGARI = "\u0930\u093e\u091c\u0947\u0936"


def read_wav(path: Path) -> tuple[int, int, int, bytes]:
    """(channels, sample width, rate, frames) of a WAV file."""
    with wave.open(str(path), "rb") as handle:
        return (
            handle.getnchannels(),
            handle.getsampwidth(),
            handle.getframerate(),
            handle.readframes(handle.getnframes()),
        )


# ---- speech to text -------------------------------------------------------------------


def test_stt_returns_nothing_by_default_so_the_slot_is_marked_by_hand(tmp_path: Path) -> None:
    """Default fake: no transcript."""
    assert FakeSpeechToText().transcribe(tmp_path / "a.wav") == []


def test_stt_returns_the_configured_words(tmp_path: Path) -> None:
    """The transcript is exactly what was given."""
    words = [Word("Krishan", 1.0, 1.4, 0.95), Word("ji", 1.5, 1.7, 0.9)]
    assert FakeSpeechToText(words).transcribe(tmp_path / "a.wav") == words


def test_stt_hands_out_copies_so_callers_cannot_change_it(tmp_path: Path) -> None:
    """Mutating one result does not change the next."""
    stt = FakeSpeechToText([Word("a", 0.0, 0.1, 1.0)])
    first = stt.transcribe(tmp_path / "a.wav")
    first.clear()
    assert len(stt.transcribe(tmp_path / "a.wav")) == 1


def test_stt_does_not_keep_a_reference_to_the_input_list(tmp_path: Path) -> None:
    """Later changes to the caller's list do not leak in."""
    source = [Word("a", 0.0, 0.1, 1.0)]
    stt = FakeSpeechToText(source)
    source.append(Word("b", 0.2, 0.3, 1.0))
    assert len(stt.transcribe(tmp_path / "a.wav")) == 1


# ---- voice ----------------------------------------------------------------------------


def test_voice_writes_a_valid_mono_16_bit_16k_wav(tmp_path: Path) -> None:
    """The output is structurally a real recording."""
    out = tmp_path / "voice.wav"
    seconds = FakeVoiceCloner().synthesize("Asha Verma", SAMPLE, out)
    channels, width, rate, frames = read_wav(out)
    assert (channels, width, rate) == (1, 2, 16000)
    assert len(frames) // 2 / rate == pytest.approx(seconds)


def test_voice_is_deterministic(tmp_path: Path) -> None:
    """Same text, same bytes and same duration."""
    one, two = tmp_path / "1.wav", tmp_path / "2.wav"
    first = FakeVoiceCloner().synthesize("Asha Verma", SAMPLE, one)
    second = FakeVoiceCloner().synthesize("Asha Verma", SAMPLE, two)
    assert first == second
    assert one.read_bytes() == two.read_bytes()


def test_longer_text_gives_longer_audio(tmp_path: Path) -> None:
    """Duration grows with the number of characters (0.05 s each)."""
    short = FakeVoiceCloner().synthesize("Asha", SAMPLE, tmp_path / "s.wav")
    long = FakeVoiceCloner().synthesize("Asha Verma Kumari", SAMPLE, tmp_path / "l.wav")
    assert long > short
    assert long - short == pytest.approx(0.05 * (len("Asha Verma Kumari") - len("Asha")), abs=1e-3)


def test_empty_text_still_gives_the_base_length(tmp_path: Path) -> None:
    """The base length of 0.3 s applies even to empty text."""
    assert FakeVoiceCloner().synthesize("", SAMPLE, tmp_path / "e.wav") == pytest.approx(
        0.3, abs=1e-3
    )


def test_devanagari_text_counts_characters_and_is_not_silent(tmp_path: Path) -> None:
    """Non-ASCII text works; the tone is audible."""
    out = tmp_path / "d.wav"
    seconds = FakeVoiceCloner().synthesize(DEVANAGARI, SAMPLE, out)
    assert seconds == pytest.approx(0.3 + 0.05 * len(DEVANAGARI), abs=1e-3)
    frames = read_wav(out)[3]
    assert any(frames)


def test_voice_never_touches_the_voice_sample(tmp_path: Path) -> None:
    """The sample path is ignored by the fake (it does not need to exist)."""
    assert not SAMPLE.exists()
    FakeVoiceCloner().synthesize("x", SAMPLE, tmp_path / "x.wav")


# ---- lip sync and quality -------------------------------------------------------------


def test_lipsync_passes_the_video_through_unchanged(tmp_path: Path) -> None:
    """M1 lip sync is a copy."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    video.write_bytes(b"\x00frames\xff" * 100)
    audio.write_bytes(b"ignored")
    FakeLipSyncer().sync(video, audio, out)
    assert out.read_bytes() == video.read_bytes()


def test_lipsync_with_a_missing_video_fails_loudly(tmp_path: Path) -> None:
    """No silent success on missing input."""
    with pytest.raises(FileNotFoundError):
        FakeLipSyncer().sync(tmp_path / "nope.mp4", tmp_path / "a.wav", tmp_path / "o.mp4")


def test_quality_checker_accepts_everything(tmp_path: Path) -> None:
    """The real checks arrive in M2."""
    assert FakeQualityChecker().check(tmp_path / "t.mp4", tmp_path / "o.mp4") == []
