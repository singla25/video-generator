"""Retry policy (B8, A4). Cases TT-AC12-P7, N1, N2, N5, E6, E12."""

from __future__ import annotations

import pytest

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.retry import (
    FailureKind,
    RetryPolicy,
    WorkerCrashedError,
    classify_exception,
    failure_code_for,
)


def test_default_policy_matches_b8() -> None:
    """TT-AC12-E6: 600 s timeout, 10 s delay, 2 attempts in total."""
    policy = RetryPolicy()
    assert policy.timeout_seconds == 600
    assert policy.delay_seconds == 10
    assert policy.max_retries == 1
    assert policy.total_attempts == 2


def test_policy_values_are_overridable() -> None:
    """TT-AC12-E6."""
    policy = RetryPolicy(timeout_seconds=5, delay_seconds=0, max_retries=3)
    assert policy.total_attempts == 4
    assert policy.delay_seconds == 0


@pytest.mark.parametrize("kind", [FailureKind.CRASH, FailureKind.TIMEOUT, FailureKind.STORAGE])
def test_retryable_kinds_get_exactly_one_retry(kind: FailureKind) -> None:
    """TT-AC12-P2, P3, P4, P7."""
    policy = RetryPolicy()
    assert policy.should_retry(kind, attempts_made=1)


@pytest.mark.parametrize("kind", [FailureKind.CRASH, FailureKind.TIMEOUT, FailureKind.STORAGE])
def test_no_third_attempt(kind: FailureKind) -> None:
    """TT-AC12-N1."""
    assert not RetryPolicy().should_retry(kind, attempts_made=2)


@pytest.mark.parametrize("kind", [FailureKind.QUALITY, FailureKind.UNEXPECTED])
def test_quality_and_unexpected_failures_are_never_retried(kind: FailureKind) -> None:
    """TT-AC12-N2, N5."""
    assert not RetryPolicy().should_retry(kind, attempts_made=1)


def test_zero_max_retries_disables_retrying() -> None:
    """TT-AC12-E6."""
    assert not RetryPolicy(max_retries=0).should_retry(FailureKind.CRASH, attempts_made=1)


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        (FailureKind.TIMEOUT, FailureCode.RENDER_TIMEOUT),
        (FailureKind.STORAGE, FailureCode.STORAGE_ERROR),
        (FailureKind.CRASH, FailureCode.INTERNAL_ERROR),
        (FailureKind.UNEXPECTED, FailureCode.INTERNAL_ERROR),
    ],
)
def test_failure_code_for_kind(kind: FailureKind, code: FailureCode) -> None:
    """TT-AC12-P3, P4, N5."""
    assert failure_code_for(kind) is code


def test_timeout_error_is_a_timeout() -> None:
    """TT-AC12-P3."""
    assert classify_exception(TimeoutError(), during_output_write=False) is FailureKind.TIMEOUT


@pytest.mark.parametrize("errno", [28, 13, 5])  # ENOSPC, EACCES, EIO
def test_oserror_while_writing_output_is_a_storage_error(errno: int) -> None:
    """TT-AC12-P4, N3 (B8)."""
    exc = OSError(errno, "boom")
    assert classify_exception(exc, during_output_write=True) is FailureKind.STORAGE


def test_oserror_outside_output_writing_is_not_a_storage_error() -> None:
    """TT-AC12-E12."""
    assert (
        classify_exception(OSError(5, "read"), during_output_write=False) is FailureKind.UNEXPECTED
    )


def test_non_oserror_while_writing_is_not_a_storage_error() -> None:
    """TT-AC12-E12."""
    assert classify_exception(ValueError("x"), during_output_write=True) is FailureKind.UNEXPECTED


def test_worker_crash_is_a_crash() -> None:
    """TT-AC12-P2."""
    assert classify_exception(WorkerCrashedError(), during_output_write=False) is FailureKind.CRASH


def test_domain_errors_are_quality_failures() -> None:
    """TT-AC12-N2."""
    exc = DomainError(FailureCode.NAME_TOO_LONG_TO_SPEAK, "too long")
    assert classify_exception(exc, during_output_write=False) is FailureKind.QUALITY


def test_arbitrary_exception_is_unexpected() -> None:
    """TT-AC12-N5."""
    assert (
        classify_exception(RuntimeError("?"), during_output_write=False) is FailureKind.UNEXPECTED
    )
