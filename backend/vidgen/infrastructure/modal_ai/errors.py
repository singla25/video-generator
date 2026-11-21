"""Errors of the remote (Modal) adapters. Messages are fixed text: no tokens, names or content."""

from __future__ import annotations

from vidgen.domain.retry import WorkerCrashedError

AUTH_FAILED_CODE = "MODAL_AUTH_FAILED"
AUTH_FAILED_MESSAGE = "The cloud AI service rejected the credentials."


class RemoteTimeoutError(TimeoutError):
    """A remote call took too long. Classified as a retryable timeout."""


class RemoteCrashError(WorkerCrashedError):
    """The remote container died or was lost. Classified as a retryable crash."""


class RemoteAuthError(Exception):
    """The remote service rejected the credentials. Never retried; the message is fixed."""

    code = AUTH_FAILED_CODE

    def __init__(self, message: str = AUTH_FAILED_MESSAGE) -> None:
        super().__init__(message)
