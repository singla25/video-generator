"""The real ``RemoteModelClient`` on Modal. ``modal`` is imported only inside functions.

Never exercised by the unit tests (no live calls); the fake client stands in for it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from vidgen.infrastructure.modal_ai.errors import (
    RemoteAuthError,
    RemoteCrashError,
    RemoteTimeoutError,
)

T = TypeVar("T")

FN_TRANSCRIBE = "transcribe"
FN_HAS_SAMPLE = "has_sample"
FN_UPLOAD_SAMPLE = "upload_sample"
FN_SYNTHESIZE = "synthesize"


def _translate(call: Callable[[], T]) -> T:
    """Run a Modal call and map Modal's exceptions to ours (messages are fixed, no details)."""
    import modal.exception as modal_exc  # lazy: optional `cloud` extra

    try:
        return call()
    except modal_exc.AuthError:
        raise RemoteAuthError() from None
    except modal_exc.FunctionTimeoutError:
        raise RemoteTimeoutError("The cloud AI call timed out.") from None
    except modal_exc.Error:
        raise RemoteCrashError("The cloud AI call failed.") from None


class ModalRemoteClient:
    """Calls deployed Modal functions of one app by name; credentials come from Modal's env."""

    def __init__(self, app_name: str) -> None:
        self._app_name = app_name

    def _fn(self, name: str) -> Any:
        import modal  # lazy: optional `cloud` extra

        return modal.Function.from_name(self._app_name, name)

    def _remote(self, name: str, *args: Any) -> Any:
        return _translate(lambda: self._fn(name).remote(*args))

    def transcribe(self, audio: bytes) -> Any:
        """Run remote speech-to-text on the audio bytes."""
        return self._remote(FN_TRANSCRIBE, audio)

    def has_sample(self, sample_hash: str) -> bool:
        """True if the sample is already in the remote volume."""
        return bool(self._remote(FN_HAS_SAMPLE, sample_hash))

    def upload_sample(self, sample_hash: str, data: bytes) -> None:
        """Store the sample in the remote volume."""
        self._remote(FN_UPLOAD_SAMPLE, sample_hash, data)

    def synthesize(self, text: str, sample_hash: str) -> bytes:
        """Run remote voice cloning; returns WAV bytes."""
        result = self._remote(FN_SYNTHESIZE, text, sample_hash)
        return bytes(result)
