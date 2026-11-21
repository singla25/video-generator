"""Extra edge cases for ModalVoiceCloner accounting and per-instance state."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.fixtures.modal_fake import FakeRemoteClient
from vidgen.domain.codes import DomainError
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner


def test_bytes_sent_counts_utf8_bytes_not_characters(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    cloner = ModalVoiceCloner(client)
    text = "नमस्ते 🎬"
    cloner.synthesize(text, sample, tmp_path / "a.wav")
    expected = sample.stat().st_size + len(text.encode("utf-8")) + 64
    assert cloner.bytes_sent == expected
    assert len(text.encode("utf-8")) > len(text)


def test_second_cloner_instance_checks_has_sample_again_but_does_not_reupload(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    ModalVoiceCloner(client).synthesize("a", sample, tmp_path / "1.wav")
    second = ModalVoiceCloner(client)
    second.synthesize("b", sample, tmp_path / "2.wav")
    assert len(client.has_sample_calls) == 2
    assert len(client.upload_calls) == 1
    assert second.bytes_sent < sample.stat().st_size  # sample not counted again


def test_failed_synthesis_does_not_count_bytes_for_the_row(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    client.wav = b"not a wav"
    cloner = ModalVoiceCloner(client)
    with pytest.raises(DomainError):
        cloner.synthesize("hello", sample, tmp_path / "x.wav")
    assert cloner.bytes_received == 0
    assert cloner.bytes_sent == sample.stat().st_size  # only the one-time upload


def test_empty_text_is_sent_with_hash_only(
    client: FakeRemoteClient, sample: Path, tmp_path: Path
) -> None:
    ModalVoiceCloner(client).synthesize("", sample, tmp_path / "e.wav")
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert client.synthesize_calls == [("", digest)]
