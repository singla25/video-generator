"""Retry policy and failure classification (B8, A4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vidgen.domain.codes import DomainError, FailureCode


class WorkerCrashedError(Exception):
    """The worker process died or was lost while rendering a row."""


class FailureKind(Enum):
    """Broad class of a failure; decides retry and the stored code."""

    CRASH = "crash"
    TIMEOUT = "timeout"
    STORAGE = "storage"
    QUALITY = "quality"
    UNEXPECTED = "unexpected"


_RETRYABLE_KINDS = frozenset({FailureKind.CRASH, FailureKind.TIMEOUT, FailureKind.STORAGE})
_CODE_BY_KIND: dict[FailureKind, FailureCode] = {
    FailureKind.CRASH: FailureCode.INTERNAL_ERROR,
    FailureKind.TIMEOUT: FailureCode.RENDER_TIMEOUT,
    FailureKind.STORAGE: FailureCode.STORAGE_ERROR,
    FailureKind.QUALITY: FailureCode.OUTPUT_CHECK_FAILED,  # fallback; DomainError carries its own
    FailureKind.UNEXPECTED: FailureCode.INTERNAL_ERROR,
}


@dataclass(frozen=True)
class RetryPolicy:
    """Row timeout and retry limits (from settings)."""

    timeout_seconds: int = 600
    delay_seconds: int = 10
    max_retries: int = 1

    @property
    def total_attempts(self) -> int:
        """First attempt plus retries."""
        return 1 + self.max_retries

    def should_retry(self, kind: FailureKind, attempts_made: int) -> bool:
        """True if a failure of ``kind`` after ``attempts_made`` attempts gets another try."""
        return kind in _RETRYABLE_KINDS and attempts_made < self.total_attempts


def failure_code_for(kind: FailureKind) -> FailureCode:
    """Failure code stored for a failure of ``kind``."""
    return _CODE_BY_KIND[kind]


def classify_exception(exc: BaseException, *, during_output_write: bool) -> FailureKind:
    """Decide the failure kind of ``exc``; OSError counts as storage only while writing (B8)."""
    if isinstance(exc, WorkerCrashedError):
        return FailureKind.CRASH
    if isinstance(exc, TimeoutError):  # before OSError: TimeoutError is a subclass of it
        return FailureKind.TIMEOUT
    if isinstance(exc, DomainError):
        return FailureKind.QUALITY
    if during_output_write and isinstance(exc, OSError):
        return FailureKind.STORAGE
    return FailureKind.UNEXPECTED
