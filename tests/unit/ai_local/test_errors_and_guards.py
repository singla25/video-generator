"""Error types, offline guard, memory guard (AC7, AC8)."""

from __future__ import annotations

import socket
import threading

import pytest

from vidgen.infrastructure.local_ai.errors import (
    AiBusyError,
    EmptyAudioError,
    LocalAiError,
    ModelWeightsMissingError,
    OfflineViolationError,
)
from vidgen.infrastructure.local_ai.guard import SingleRenderGuard
from vidgen.infrastructure.local_ai.offline import offline_only
from vidgen.services.render_support import classify_failure


@pytest.mark.parametrize(
    "error", [ModelWeightsMissingError, EmptyAudioError, OfflineViolationError, AiBusyError]
)
def test_every_local_ai_error_derives_from_the_base_error(error: type[Exception]) -> None:
    assert issubclass(error, LocalAiError)


def test_local_ai_error_is_classified_so_the_row_fails_alone() -> None:
    """The batch runner turns any adapter error into a stored row failure code."""
    kind, code = classify_failure(ModelWeightsMissingError("whisper"), publishing=False)
    assert code.value
    assert kind is not None


def test_offline_guard_blocks_outgoing_connections() -> None:
    with offline_only(), pytest.raises(OfflineViolationError):
        socket.create_connection(("example.com", 443), timeout=1)


def test_offline_guard_blocks_dns_lookups() -> None:
    with offline_only(), pytest.raises(OfflineViolationError):
        socket.getaddrinfo("example.com", 443)


def test_offline_guard_is_removed_on_exit_even_after_an_error() -> None:
    original = socket.create_connection
    with pytest.raises(RuntimeError), offline_only():
        raise RuntimeError("boom")
    assert socket.create_connection is original


def test_second_concurrent_render_is_rejected_by_the_memory_guard() -> None:
    guard = SingleRenderGuard()
    with guard.acquire(), pytest.raises(AiBusyError), guard.acquire():
        pass


def test_guard_is_released_after_a_failed_render() -> None:
    guard = SingleRenderGuard()
    with pytest.raises(ValueError), guard.acquire():
        raise ValueError("render failed")
    with guard.acquire():
        pass


def test_guard_rejects_a_render_started_from_another_thread() -> None:
    guard = SingleRenderGuard()
    results: list[bool] = []

    def other() -> None:
        try:
            with guard.acquire():
                results.append(True)
        except AiBusyError:
            results.append(False)

    with guard.acquire():
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(timeout=5)
    assert results == [False]
