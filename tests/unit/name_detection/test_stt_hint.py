"""The optional ``hint`` on the speech-to-text port and its three adapters (AC6)."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.doubles import FakeSpeechToText
from tests.fixtures.modal_fake import FakeRemoteClient, make_wav_bytes
from tests.unit.ai_local.conftest import write_wav
from vidgen.infrastructure.local_ai.stt import FasterWhisperSpeechToText
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText
from vidgen.ports.interfaces import SpeechToText


class Seg:
    words: list[Any]

    def __init__(self) -> None:
        self.words = []


class RecordingWhisper:
    """Stub faster-whisper model that records the keyword arguments of each call."""

    def __init__(self) -> None:
        self.kwargs: list[dict[str, Any]] = []

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[list[Seg], object]:
        self.kwargs.append(kwargs)
        return [Seg()], object()


def local(tmp_path: Path) -> tuple[FasterWhisperSpeechToText, RecordingWhisper, Path]:
    model = RecordingWhisper()
    weights = tmp_path / "w"
    weights.mkdir()
    (weights / "x.bin").write_bytes(b"x")
    stt = FasterWhisperSpeechToText(weights, loader=lambda _p: model)
    return stt, model, write_wav(tmp_path / "a.wav")


def test_port_declares_an_optional_hint_defaulting_to_none() -> None:
    parameter = inspect.signature(SpeechToText.transcribe).parameters["hint"]
    assert parameter.default is None


def test_local_adapter_forwards_the_hint_as_hotwords(tmp_path: Path) -> None:
    stt, model, audio = local(tmp_path)
    stt.transcribe(audio, hint="Krishan")
    assert model.kwargs[0]["hotwords"] == "Krishan"
    assert model.kwargs[0]["word_timestamps"] is True  # existing behaviour kept


def test_local_adapter_forwards_a_devanagari_hint_unchanged(tmp_path: Path) -> None:
    stt, model, audio = local(tmp_path)
    stt.transcribe(audio, hint="कृष्ण")
    assert model.kwargs[0]["hotwords"] == "कृष्ण"


def test_local_adapter_sends_no_hotwords_without_a_hint(tmp_path: Path) -> None:
    stt, model, audio = local(tmp_path)
    stt.transcribe(audio)
    stt.transcribe(audio, hint=None)
    assert all("hotwords" not in kwargs for kwargs in model.kwargs)


@pytest.mark.parametrize("hint", ["", None])
def test_local_adapter_sends_no_hotwords_for_an_empty_hint(
    tmp_path: Path, hint: str | None
) -> None:
    stt, model, audio = local(tmp_path)
    stt.transcribe(audio, hint=hint)
    assert "hotwords" not in model.kwargs[0]


def test_local_adapter_accepts_the_hint_positionally(tmp_path: Path) -> None:
    stt, model, audio = local(tmp_path)
    stt.transcribe(audio, "Krishan")
    assert model.kwargs[0]["hotwords"] == "Krishan"


def test_modal_adapter_accepts_and_ignores_the_hint(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    audio = tmp_path / "speech.wav"
    audio.write_bytes(make_wav_bytes(1.0))
    adapter = ModalSpeechToText(client)
    with_hint = adapter.transcribe(audio, hint="Krishan")
    without = adapter.transcribe(audio)
    assert with_hint == without
    assert client.transcribe_calls == [audio.read_bytes()] * 2


def test_fake_adapter_accepts_the_hint(tmp_path: Path) -> None:
    fake = FakeSpeechToText()
    fake.transcribe(tmp_path / "a.wav", hint="Krishan")
    fake.transcribe(tmp_path / "a.wav")
    assert fake.hints == ["Krishan", None]
