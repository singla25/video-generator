"""ModalRemoteClient against a stubbed `modal` module (no real import, no network)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from vidgen.infrastructure.modal_ai.errors import (
    RemoteAuthError,
    RemoteCrashError,
    RemoteTimeoutError,
)
from vidgen.infrastructure.modal_ai.modal_client import ModalRemoteClient

SECRET = "ak-SECRET-TOKEN-123"  # noqa: S105 - synthetic


class _Error(Exception):
    pass


class _AuthError(_Error):
    pass


class _TimeoutError(_Error):
    pass


class _FakeFn:
    def __init__(self, result: Any = None, raises: Exception | None = None) -> None:
        self.result, self.raises, self.calls = result, raises, []

    def remote(self, *args: Any) -> Any:
        self.calls.append(args)
        if self.raises:
            raise self.raises
        return self.result


class _Stub:
    def __init__(self) -> None:
        self.lookups: list[tuple[str, str]] = []
        self.fn = _FakeFn()
        self.lookup_error: Exception | None = None


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> _Stub:
    s = _Stub()
    modal = types.ModuleType("modal")
    exc = types.ModuleType("modal.exception")
    exc.Error = _Error  # type: ignore[attr-defined]
    exc.AuthError = _AuthError  # type: ignore[attr-defined]
    exc.FunctionTimeoutError = _TimeoutError  # type: ignore[attr-defined]

    def from_name(app: str, name: str) -> _FakeFn:
        s.lookups.append((app, name))
        if s.lookup_error:
            raise s.lookup_error
        return s.fn

    modal.Function = types.SimpleNamespace(from_name=from_name)  # type: ignore[attr-defined]
    modal.exception = exc  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)
    monkeypatch.setitem(sys.modules, "modal.exception", exc)
    return s


def test_transcribe_calls_named_function_with_audio_and_returns_result(stub: _Stub) -> None:
    stub.fn.result = {"text": "hi"}
    assert ModalRemoteClient("app1").transcribe(b"aud") == {"text": "hi"}
    assert stub.lookups == [("app1", "transcribe")]
    assert stub.fn.calls == [(b"aud",)]


@pytest.mark.parametrize("value", [True, False])
def test_has_sample_calls_function_and_returns_bool(stub: _Stub, value: bool) -> None:
    stub.fn.result = 1 if value else 0
    assert ModalRemoteClient("a").has_sample("h1") is value
    assert stub.lookups == [("a", "has_sample")]
    assert stub.fn.calls == [("h1",)]


def test_upload_sample_passes_hash_and_data_returns_none(stub: _Stub) -> None:
    assert ModalRemoteClient("a").upload_sample("h", b"data") is None
    assert stub.lookups == [("a", "upload_sample")]
    assert stub.fn.calls == [("h", b"data")]


def test_synthesize_passes_text_and_hash_and_returns_bytes(stub: _Stub) -> None:
    stub.fn.result = bytearray(b"RIFFwav")
    out = ModalRemoteClient("a").synthesize("héllo 🎬", "h")
    assert out == b"RIFFwav" and type(out) is bytes
    assert stub.lookups == [("a", "synthesize")]
    assert stub.fn.calls == [("héllo 🎬", "h")]


CALLS = {
    "transcribe": lambda c: c.transcribe(b"x"),
    "has_sample": lambda c: c.has_sample("h"),
    "upload_sample": lambda c: c.upload_sample("h", b"x"),
    "synthesize": lambda c: c.synthesize("t", "h"),
}


@pytest.mark.parametrize("method", list(CALLS))
def test_auth_error_becomes_fixed_remote_auth_error_without_cause(stub: _Stub, method: str) -> None:
    stub.fn.raises = _AuthError(f"bad token {SECRET}")
    with pytest.raises(RemoteAuthError) as ei:
        CALLS[method](ModalRemoteClient("a"))
    err = ei.value
    assert SECRET not in str(err) and SECRET not in repr(err)
    assert err.__cause__ is None and err.__suppress_context__
    # __context__ is kept by Python but hidden from tracebacks via __suppress_context__
    import traceback

    assert SECRET not in "".join(traceback.format_exception(err))


@pytest.mark.parametrize("method", list(CALLS))
def test_function_timeout_becomes_remote_timeout_error(stub: _Stub, method: str) -> None:
    stub.fn.raises = _TimeoutError("took 900s")
    with pytest.raises(RemoteTimeoutError) as ei:
        CALLS[method](ModalRemoteClient("a"))
    assert "900" not in str(ei.value) and ei.value.__cause__ is None


@pytest.mark.parametrize("method", list(CALLS))
def test_other_modal_error_becomes_remote_crash_error(stub: _Stub, method: str) -> None:
    stub.fn.raises = _Error(f"boom {SECRET}")
    with pytest.raises(RemoteCrashError) as ei:
        CALLS[method](ModalRemoteClient("a"))
    assert SECRET not in str(ei.value) and ei.value.__cause__ is None


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (_AuthError("x"), RemoteAuthError),
        (_TimeoutError("x"), RemoteTimeoutError),
        (_Error("x"), RemoteCrashError),
    ],
)
def test_lookup_failure_in_from_name_is_translated(
    stub: _Stub, raised: Exception, expected: type[Exception]
) -> None:
    stub.lookup_error = raised
    with pytest.raises(expected):
        ModalRemoteClient("a").has_sample("h")


def test_non_modal_exception_is_not_swallowed(stub: _Stub) -> None:
    stub.fn.raises = ValueError("programming bug")
    with pytest.raises(ValueError):
        ModalRemoteClient("a").transcribe(b"x")


def test_app_name_is_used_for_every_lookup(stub: _Stub) -> None:
    c = ModalRemoteClient("my-app")
    c.has_sample("h")
    c.upload_sample("h", b"")
    assert {a for a, _ in stub.lookups} == {"my-app"}


def test_empty_audio_and_empty_data_are_passed_through(stub: _Stub) -> None:
    c = ModalRemoteClient("a")
    c.transcribe(b"")
    c.upload_sample("h", b"")
    assert stub.fn.calls == [(b"",), ("h", b"")]
