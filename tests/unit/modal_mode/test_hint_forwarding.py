"""AC6: the speech-to-text hint travels adapter -> client -> remote function."""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.modal_fake import FakeRemoteClient, make_wav_bytes
from vidgen.infrastructure.modal_ai.client import RemoteModelClient
from vidgen.infrastructure.modal_ai.modal_client import ModalRemoteClient
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText

HINTS = ["Sahil Singla", "सहिल", "Zoë 🎬", "x" * 5000, "", None]
HINT_IDS = ["ascii", "devanagari", "emoji", "very-long", "empty", "none"]


class _Fn:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def remote(self, *args: Any) -> Any:
        self.calls.append(args)
        return []


@pytest.fixture
def remote_fn(monkeypatch: pytest.MonkeyPatch) -> _Fn:
    fn = _Fn()
    modal = types.ModuleType("modal")
    exc = types.ModuleType("modal.exception")
    for name in ("Error", "AuthError", "FunctionTimeoutError"):
        setattr(exc, name, type(name, (Exception,), {}))
    modal.Function = types.SimpleNamespace(from_name=lambda app, name: fn)  # type: ignore[attr-defined]
    modal.exception = exc  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "modal.exception", exc)
    return fn


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "a.wav"
    path.write_bytes(make_wav_bytes(0.5))
    return path


def test_protocol_transcribe_accepts_an_optional_hint() -> None:
    params = inspect.signature(RemoteModelClient.transcribe).parameters
    assert list(params) == ["self", "audio", "hint"]
    assert params["hint"].default is None


def test_fake_client_records_the_hint() -> None:
    client = FakeRemoteClient()
    client.transcribe(b"a", "Asha")
    client.transcribe(b"b")
    assert client.transcribe_hints == ["Asha", None]


@pytest.mark.parametrize("hint", HINTS, ids=HINT_IDS)
def test_the_adapter_forwards_the_hint_to_the_client(hint: str | None, audio: Path) -> None:
    client = FakeRemoteClient()
    ModalSpeechToText(client).transcribe(audio, hint)
    assert client.transcribe_hints == [hint]


def test_the_adapter_without_a_hint_sends_none(audio: Path) -> None:
    client = FakeRemoteClient()
    ModalSpeechToText(client).transcribe(audio)
    assert client.transcribe_hints == [None]


@pytest.mark.parametrize("hint", HINTS, ids=HINT_IDS)
def test_the_real_client_passes_audio_and_hint_to_the_remote_call(
    remote_fn: _Fn, hint: str | None
) -> None:
    ModalRemoteClient("app").transcribe(b"aud", hint)
    assert remote_fn.calls == [(b"aud", hint)]


def test_the_real_client_sends_none_when_no_hint_is_given(remote_fn: _Fn) -> None:
    ModalRemoteClient("app").transcribe(b"aud")
    assert remote_fn.calls == [(b"aud", None)]
