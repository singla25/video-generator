"""Shared doubles for the local-AI tests: stub models, settings, tiny WAV files.

No test here imports torch or loads weights. ``local_ai`` smoke tests are skipped unless
``RUN_LOCAL_AI=1`` is set in the environment.
"""

from __future__ import annotations

import os
import secrets
import wave
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from vidgen.settings import Settings


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker (the root pyproject is outside the tester's domain)."""
    config.addinivalue_line(
        "markers", "local_ai: real-model smoke test, skipped unless RUN_LOCAL_AI=1"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip real-model tests by default and in CI."""
    if os.environ.get("RUN_LOCAL_AI") == "1":
        return
    skip = pytest.mark.skip(reason="real-model smoke test; set RUN_LOCAL_AI=1")
    for item in items:
        if "local_ai" in item.keywords:
            item.add_marker(skip)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Settings with random fake secrets and a throwaway model directory."""
    values: dict[str, Any] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("not-a-real-hash"),
        "storage_root": tmp_path / "media",
        "cookie_secure": False,
        "local_ai_weights_dir": tmp_path / "weights",
    }
    values.update(overrides)
    return Settings(**values)


def write_wav(path: Path, seconds: float = 0.5, rate: int = 16000) -> Path:
    """Write a silent mono 16-bit WAV (``seconds`` may be 0 for an empty file)."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


@pytest.fixture
def weights_dir(tmp_path: Path) -> Path:
    """A model directory that exists and holds one placeholder file."""
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "placeholder.bin").write_bytes(b"x")
    return folder


@pytest.fixture
def missing_weights(tmp_path: Path) -> Path:
    """A model directory that does not exist."""
    return tmp_path / "no-such-weights"
