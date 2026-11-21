"""ModalVoiceCloner: upload-once sample, text+hash per row, atomic wav output."""

from __future__ import annotations

import hashlib
import logging
import threading
import wave
from pathlib import Path

import pytest

from tests.fixtures.modal_fake import DEMO_TOKEN, FakeRemoteClient, make_wav_bytes
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.retry import FailureKind, RetryPolicy, classify_exception
from vidgen.infrastructure.modal_ai.errors import (
    RemoteAuthError,
    RemoteCrashError,
    RemoteTimeoutError,
)
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthesize_writes_wav_and_returns_its_duration(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.wav"
    seconds = ModalVoiceCloner(client).synthesize("Demo", sample, out)
    assert seconds == pytest.approx(1.5, abs=0.01)
    assert out.read_bytes() == client.wav
    with wave.open(str(out), "rb") as handle:
        assert handle.getnframes() > 0


def test_sample_is_uploaded_once_across_many_rows_and_rows_send_only_text_and_hash(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    cloner = ModalVoiceCloner(client)
    for index in range(5):
        cloner.synthesize(f"Name {index}", sample, tmp_path / f"o{index}.wav")
    assert client.upload_calls == [_hash(sample)]
    assert client.synthesize_calls == [(f"Name {i}", _hash(sample)) for i in range(5)]


def test_sample_already_on_remote_is_not_uploaded(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    client.samples[_hash(sample)] = sample.read_bytes()
    ModalVoiceCloner(client).synthesize("Demo", sample, tmp_path / "o.wav")
    assert client.upload_calls == []


def test_two_adapters_sharing_one_client_upload_the_sample_once(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    ModalVoiceCloner(client).synthesize("A", sample, tmp_path / "a.wav")
    ModalVoiceCloner(client).synthesize("B", sample, tmp_path / "b.wav")
    assert client.upload_calls == [_hash(sample)]


def test_changed_sample_content_is_uploaded_again(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    cloner = ModalVoiceCloner(client)
    cloner.synthesize("A", sample, tmp_path / "a.wav")
    sample.write_bytes(make_wav_bytes(3.0))
    cloner.synthesize("A", sample, tmp_path / "b.wav")
    assert len(client.upload_calls) == 2


def test_concurrent_synthesize_with_same_new_sample_uploads_exactly_once(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    """One cloner instance serialises the check-then-upload; pinned as exactly once."""
    client.upload_delay_s = 0.05
    cloner = ModalVoiceCloner(client)
    threads = [
        threading.Thread(target=cloner.synthesize, args=(f"N{i}", sample, tmp_path / f"{i}.wav"))
        for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert client.upload_calls == [_hash(sample)]
    assert len(client.synthesize_calls) == 6


def test_bytes_accounting_counts_sample_once_text_per_row_and_wav_down(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    cloner = ModalVoiceCloner(client)
    cloner.synthesize("ab", sample, tmp_path / "1.wav")
    cloner.synthesize("cd", sample, tmp_path / "2.wav")
    assert cloner.bytes_sent >= sample.stat().st_size
    assert cloner.bytes_sent < 2 * sample.stat().st_size  # not re-sent per row
    assert cloner.bytes_received == 2 * len(client.wav)


def test_unicode_devanagari_text_is_sent_unchanged(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    ModalVoiceCloner(client).synthesize("सहिल कुमार", sample, tmp_path / "o.wav")
    assert client.synthesize_calls[0][0] == "सहिल कुमार"


def test_very_long_text_is_passed_through(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    text = "नाम " * 5000
    ModalVoiceCloner(client).synthesize(text, sample, tmp_path / "o.wav")
    assert client.synthesize_calls[0][0] == text


def test_missing_sample_raises_file_not_found_without_remote_call(
    client: FakeRemoteClient, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        ModalVoiceCloner(client).synthesize("A", tmp_path / "none.wav", tmp_path / "o.wav")
    assert client.synthesize_calls == [] and client.upload_calls == []


@pytest.mark.parametrize("bad", [b"", b"garbage not a wav", make_wav_bytes(0.0)])
def test_empty_or_garbled_audio_raises_tts_failed_and_leaves_no_file(
    client: FakeRemoteClient, sample: Path, tmp_path: Path, bad: bytes
) -> None:
    client.wav = bad
    out = tmp_path / "out" / "o.wav"
    out.parent.mkdir()
    with pytest.raises(DomainError) as info:
        ModalVoiceCloner(client).synthesize("A", sample, out)
    assert info.value.code is FailureCode.TTS_FAILED
    assert list(out.parent.iterdir()) == []  # no output, no temp file


def test_failure_keeps_an_existing_output_untouched(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    out = tmp_path / "o.wav"
    out.write_bytes(b"previous")
    client.error = RemoteCrashError("died")
    with pytest.raises(RemoteCrashError):
        ModalVoiceCloner(client).synthesize("A", sample, out)
    assert out.read_bytes() == b"previous"


def test_timeout_and_crash_are_retryable_kinds(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    for error, expected in (
        (RemoteTimeoutError("slow"), FailureKind.TIMEOUT),
        (RemoteCrashError("died"), FailureKind.CRASH),
    ):
        client.error = error
        with pytest.raises(type(error)) as info:
            ModalVoiceCloner(client).synthesize("A", sample, tmp_path / "o.wav")
        kind = classify_exception(info.value, during_output_write=False)
        assert kind is expected and RetryPolicy().should_retry(kind, 1)
        assert not (tmp_path / "o.wav").exists()


def test_auth_failure_is_non_retryable_and_never_leaks_the_token(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    client.error = RemoteAuthError(f"bad credentials {DEMO_TOKEN}")
    with pytest.raises(RemoteAuthError) as info:
        ModalVoiceCloner(client).synthesize("A", sample, tmp_path / "o.wav")
    err = info.value
    assert DEMO_TOKEN not in str(err) and DEMO_TOKEN not in repr(err)
    assert err.__cause__ is None and err.__suppress_context__
    assert not RetryPolicy().should_retry(classify_exception(err, during_output_write=False), 1)


def test_logs_carry_no_name_text_or_token(
    client: FakeRemoteClient, sample: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        ModalVoiceCloner(client).synthesize("Zorblax Demo", sample, tmp_path / "o.wav")
        client.error = RemoteAuthError(f"x {DEMO_TOKEN}")
        with pytest.raises(RemoteAuthError):
            ModalVoiceCloner(client).synthesize("Zorblax Demo", sample, tmp_path / "p.wav")
    logged = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "Zorblax" not in logged and DEMO_TOKEN not in logged
