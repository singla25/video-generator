"""RemoteAuthError must carry no link to the original exception (ADR-013 secrecy).

Not just suppressed: `__cause__ is None` AND `__context__ is None`, the token is absent
from the whole chain and from the formatted traceback.
"""

from __future__ import annotations

import sys
import traceback
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.modal_fake import DEMO_TOKEN, FakeRemoteClient
from vidgen.infrastructure.modal_ai.errors import (
    RemoteAuthError,
    RemoteCrashError,
    RemoteTimeoutError,
)
from vidgen.infrastructure.modal_ai.modal_client import ModalRemoteClient
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner

TOKEN = "ak-SECRET-TOKEN-456"  # noqa: S105 - synthetic


def _chain(err: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    stack: list[BaseException | None] = [err]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        yield e
        stack.extend([e.__cause__, e.__context__])


def _assert_unlinked(err: BaseException, token: str) -> None:
    assert err.__cause__ is None
    assert err.__context__ is None
    for e in _chain(err):
        assert token not in str(e) and token not in repr(e) and token not in repr(e.args)
    assert token not in "".join(traceback.format_exception(err))


# --- scope: _guard.call_remote (adapters over a client that raises RemoteAuthError) ---


def test_stt_auth_error_has_no_cause_and_no_context(client: FakeRemoteClient, audio: Path) -> None:
    client.error = RemoteAuthError(f"bad credentials {DEMO_TOKEN}")
    with pytest.raises(RemoteAuthError) as ei:
        ModalSpeechToText(client).transcribe(audio)
    _assert_unlinked(ei.value, DEMO_TOKEN)


def test_tts_synthesize_auth_error_has_no_cause_and_no_context(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    client.error = RemoteAuthError(f"bad credentials {DEMO_TOKEN}")
    with pytest.raises(RemoteAuthError) as ei:
        ModalVoiceCloner(client).synthesize("A", sample, tmp_path / "o.wav")
    _assert_unlinked(ei.value, DEMO_TOKEN)


def test_tts_upload_path_auth_error_has_no_cause_and_no_context(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    # Fail on the sample-upload step only (has_sample says "missing", then upload raises).
    def boom(sample_hash: str, data: bytes) -> None:
        raise RemoteAuthError(f"bad credentials {DEMO_TOKEN}")

    client.upload_sample = boom  # type: ignore[method-assign]
    with pytest.raises(RemoteAuthError) as ei:
        ModalVoiceCloner(client).synthesize("A", sample, tmp_path / "o.wav")
    _assert_unlinked(ei.value, DEMO_TOKEN)


# --- scope: modal_client._translate (stub `modal` module) ---


class _Error(Exception):
    pass


class _AuthError(_Error):
    pass


class _TimeoutError(_Error):
    pass


class _Fn:
    def __init__(self, raises: Exception) -> None:
        self.raises = raises

    def remote(self, *args: Any) -> Any:
        raise self.raises


@pytest.fixture
def stub_modal(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    state = types.SimpleNamespace(raises=_Error("x"))
    modal = types.ModuleType("modal")
    exc = types.ModuleType("modal.exception")
    exc.Error = _Error  # type: ignore[attr-defined]
    exc.AuthError = _AuthError  # type: ignore[attr-defined]
    exc.FunctionTimeoutError = _TimeoutError  # type: ignore[attr-defined]
    modal.Function = types.SimpleNamespace(  # type: ignore[attr-defined]
        from_name=lambda app, name: _Fn(state.raises)
    )
    modal.exception = exc  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "modal.exception", exc)
    return state


def test_translate_auth_error_has_no_cause_and_no_context(
    stub_modal: types.SimpleNamespace,
) -> None:
    stub_modal.raises = _AuthError(f"bad token {TOKEN}")
    with pytest.raises(RemoteAuthError) as ei:
        ModalRemoteClient("a").has_sample("h")
    _assert_unlinked(ei.value, TOKEN)


# Extra scope proposed by tester: same hardening for the other fixed-message errors.
@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (_TimeoutError(f"took {TOKEN}"), RemoteTimeoutError),
        (_Error(f"boom {TOKEN}"), RemoteCrashError),
    ],
)
def test_translate_timeout_and_crash_have_no_cause_and_no_context_extra_scope(
    stub_modal: types.SimpleNamespace, raised: Exception, expected: type[Exception]
) -> None:
    stub_modal.raises = raised
    with pytest.raises(expected) as ei:
        ModalRemoteClient("a").transcribe(b"x")
    _assert_unlinked(ei.value, TOKEN)
