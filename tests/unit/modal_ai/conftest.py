"""Fixtures for the Modal adapter tests (fake client only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.modal_fake import FakeRemoteClient, make_wav_bytes


@pytest.fixture
def client() -> FakeRemoteClient:
    """A fresh fake remote client."""
    return FakeRemoteClient()


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    """A small demo WAV."""
    path = tmp_path / "speech.wav"
    path.write_bytes(make_wav_bytes(1.0))
    return path


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    """A demo voice sample."""
    path = tmp_path / "voice.wav"
    path.write_bytes(make_wav_bytes(2.0))
    return path
