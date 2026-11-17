"""ModalSpeechToText: maps remote words to the domain, fails clearly (ADR-013 decisions 2-3)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.modal_fake import DEMO_TOKEN, FakeRemoteClient, good_words
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.retry import FailureKind, RetryPolicy, classify_exception
from vidgen.domain.values import Word
from vidgen.infrastructure.local_ai.errors import EmptyAudioError
from vidgen.infrastructure.modal_ai.errors import (
    RemoteAuthError,
    RemoteCrashError,
    RemoteTimeoutError,
)
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText


def test_transcribe_maps_remote_dicts_to_words_with_one_call(
    client: FakeRemoteClient, audio: Path
) -> None:
    words = ModalSpeechToText(client).transcribe(audio)
    assert words == [Word("namaste", 0.0, 0.5, 0.9), Word("Demo", 0.5, 1.0, 0.8)]
    assert client.transcribe_calls == [audio.read_bytes()]


def test_transcribe_silence_returns_empty_list(client: FakeRemoteClient, audio: Path) -> None:
    client.words = []
    assert ModalSpeechToText(client).transcribe(audio) == []


def test_transcribe_keeps_devanagari_text(client: FakeRemoteClient, audio: Path) -> None:
    client.words = [{"text": "सहिल", "start_s": 0.1, "end_s": 0.4, "confidence": 0.7}]
    assert ModalSpeechToText(client).transcribe(audio)[0].text == "सहिल"


def test_bytes_accounting_counts_audio_up_and_result_down(
    client: FakeRemoteClient, audio: Path
) -> None:
    adapter = ModalSpeechToText(client)
    adapter.transcribe(audio)
    adapter.transcribe(audio)
    assert adapter.bytes_sent == 2 * audio.stat().st_size
    assert adapter.bytes_received > 0


def test_missing_audio_file_raises_file_not_found_and_makes_no_remote_call(
    client: FakeRemoteClient, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        ModalSpeechToText(client).transcribe(tmp_path / "nope.wav")
    assert client.transcribe_calls == []


def test_empty_audio_file_raises_empty_audio_error(
    client: FakeRemoteClient, tmp_path: Path
) -> None:
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(EmptyAudioError):
        ModalSpeechToText(client).transcribe(empty)
    assert client.transcribe_calls == []


@pytest.mark.parametrize(
    "bad",
    [
        "not a list",
        None,
        [{"text": "x", "start_s": 0.0, "end_s": 1.0}],  # confidence missing
        [{"text": "x", "start_s": "a", "end_s": 1.0, "confidence": 0.5}],
        [{"text": "x", "start_s": 2.0, "end_s": 1.0, "confidence": 0.5}],  # end before start
        [{"text": 5, "start_s": 0.0, "end_s": 1.0, "confidence": 0.5}],
        [{"text": "x", "start_s": 0.0, "end_s": 1.0, "confidence": 1.5}],  # out of range
        ["word"],
    ],
)
def test_malformed_remote_result_raises_coded_stt_failed(
    client: FakeRemoteClient, audio: Path, bad: Any
) -> None:
    client.words = bad
    with pytest.raises(DomainError) as info:
        ModalSpeechToText(client).transcribe(audio)
    assert info.value.code is FailureCode.STT_FAILED


def test_timeout_is_retryable_timeout_kind(client: FakeRemoteClient, audio: Path) -> None:
    client.error = RemoteTimeoutError("took too long")
    with pytest.raises(RemoteTimeoutError) as info:
        ModalSpeechToText(client).transcribe(audio)
    kind = classify_exception(info.value, during_output_write=False)
    assert kind is FailureKind.TIMEOUT and RetryPolicy().should_retry(kind, 1)


def test_remote_crash_is_retryable_crash_kind(client: FakeRemoteClient, audio: Path) -> None:
    client.error = RemoteCrashError("container died")
    with pytest.raises(RemoteCrashError) as info:
        ModalSpeechToText(client).transcribe(audio)
    kind = classify_exception(info.value, during_output_write=False)
    assert kind is FailureKind.CRASH and RetryPolicy().should_retry(kind, 1)


def test_auth_failure_is_not_retryable_and_message_has_no_token(
    client: FakeRemoteClient, audio: Path
) -> None:
    client.error = RemoteAuthError(f"denied for {DEMO_TOKEN}")
    with pytest.raises(RemoteAuthError) as info:
        ModalSpeechToText(client).transcribe(audio)
    err = info.value
    assert DEMO_TOKEN not in str(err) and DEMO_TOKEN not in repr(err)
    assert err.__cause__ is None and err.__suppress_context__
    kind = classify_exception(err, during_output_write=False)
    assert not RetryPolicy().should_retry(kind, 1)
    assert err.code  # coded, e.g. "MODAL_AUTH_FAILED"


def test_logs_carry_no_transcript_text_or_token(
    client: FakeRemoteClient, audio: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client.words = good_words()
    with caplog.at_level(logging.DEBUG):
        ModalSpeechToText(client).transcribe(audio)
        client.error = RemoteAuthError(f"x {DEMO_TOKEN}")
        with pytest.raises(RemoteAuthError):
            ModalSpeechToText(client).transcribe(audio)
    logged = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "namaste" not in logged and "Demo" not in logged and DEMO_TOKEN not in logged
