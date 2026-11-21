"""AC4: the modal adapter factory (no `modal` import until a remote call is made)."""

from __future__ import annotations

import importlib
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.modal_fake import FakeRemoteClient, make_wav_bytes
from tests.unit.ai_local.conftest import make_settings
from tests.unit.modal_mode.conftest import ROOT
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.values import Word
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner


def build_modal_adapters(*args: Any, **kwargs: Any) -> Any:
    """Import late so a missing module fails each test, not the collection."""
    from vidgen.infrastructure.modal_ai.factory import build_modal_adapters as build

    return build(*args, **kwargs)


def UnavailableLipSyncer() -> Any:  # noqa: N802
    """Import late (see above)."""
    module = importlib.import_module("vidgen.infrastructure.modal_ai.lipsync")
    return module.UnavailableLipSyncer()


LIPSYNC_TEXT = "Lip sync on the cloud is not available yet."


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "a.wav"
    path.write_bytes(make_wav_bytes(0.5))
    return path


def test_the_factory_builds_the_modal_speech_and_voice_adapters(modal_settings: Any) -> None:
    adapters = build_modal_adapters(modal_settings, client=FakeRemoteClient())
    assert isinstance(adapters.stt, ModalSpeechToText)
    assert isinstance(adapters.voice, ModalVoiceCloner)


def test_the_adapters_use_the_injected_client(modal_settings: Any, audio: Path) -> None:
    client = FakeRemoteClient()
    words = build_modal_adapters(modal_settings, client=client).stt.transcribe(audio, "Asha")
    assert words and isinstance(words[0], Word)
    assert client.transcribe_hints == ["Asha"]


def test_without_a_client_the_real_one_uses_the_configured_app_name(
    tmp_path: Path, audio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookups: list[tuple[str, str]] = []

    class Fn:
        def remote(self, *args: Any) -> Any:
            return []

    modal = types.ModuleType("modal")
    exc = types.ModuleType("modal.exception")
    for name in ("Error", "AuthError", "FunctionTimeoutError"):
        setattr(exc, name, type(name, (Exception,), {}))

    def from_name(app: str, name: str) -> Fn:
        lookups.append((app, name))
        return Fn()

    modal.Function = types.SimpleNamespace(from_name=from_name)  # type: ignore[attr-defined]
    modal.exception = exc  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "modal.exception", exc)
    settings = make_settings(tmp_path, ai_mode="modal", modal_app_name="custom-app")
    build_modal_adapters(settings).stt.transcribe(audio)
    assert lookups == [("custom-app", "transcribe")]


def test_building_the_adapters_does_not_import_modal(
    modal_settings: Any, without_modal: None
) -> None:
    adapters = build_modal_adapters(modal_settings)
    assert adapters.stt is not None and adapters.voice is not None
    assert sys.modules.get("modal") is None  # still blocked: never imported


def test_a_remote_call_without_the_package_fails_with_import_error(
    modal_settings: Any, without_modal: None, audio: Path
) -> None:
    with pytest.raises(ImportError):
        build_modal_adapters(modal_settings).stt.transcribe(audio)


def test_importing_the_factory_in_a_fresh_process_does_not_import_modal() -> None:
    code = (
        "import sys\n"
        "import vidgen.infrastructure.modal_ai.factory\n"
        "raise SystemExit(1 if 'modal' in sys.modules else 0)\n"
    )
    done = subprocess.run(  # noqa: S603 - fixed argv, no network
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert done.returncode == 0, done.stderr


# --- lip sync: never a silent fake ----------------------------------------------------------------


def test_lip_sync_in_modal_mode_is_the_unavailable_syncer(modal_settings: Any) -> None:
    adapters = build_modal_adapters(modal_settings, client=FakeRemoteClient())
    assert type(adapters.lipsync).__name__ == "UnavailableLipSyncer"


def test_unavailable_lip_sync_raises_a_clear_domain_error(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    with pytest.raises(DomainError) as caught:
        UnavailableLipSyncer().sync(tmp_path / "v.mp4", tmp_path / "a.wav", out)
    assert caught.value.message == LIPSYNC_TEXT
    assert isinstance(caught.value.code, FailureCode)
    assert caught.value.code is not FailureCode.LIPSYNC_LOW_QUALITY  # would mislead the Admin
    assert not out.exists()


@pytest.mark.parametrize("start_s", [0.0, 1.5])
def test_unavailable_lip_sync_raises_whatever_the_arguments(tmp_path: Path, start_s: float) -> None:
    with pytest.raises(DomainError):
        UnavailableLipSyncer().sync(
            tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4", start_s, tmp_path / "k.mp4"
        )
