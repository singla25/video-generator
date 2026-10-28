"""AC1, AC2, AC8, AC9: AI_MODE selects fake or local adapters; fake needs no heavy libraries."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.unit.ai_local.conftest import make_settings
from vidgen.infrastructure.fakes.adapters import (
    FakeLipSyncer,
    FakeSpeechToText,
    FakeVoiceCloner,
)
from vidgen.infrastructure.local_ai.factory import (
    build_ai_adapters,
    describe_mode,
    effective_worker_threads,
)


def test_ai_mode_defaults_to_fake(tmp_path: Path) -> None:
    assert make_settings(tmp_path).ai_mode == "fake"


def test_ai_mode_is_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDGEN_AI_MODE", "local")
    assert make_settings(tmp_path).ai_mode == "local"


@pytest.mark.parametrize("value", ["real", "LOCAL ", "gpu", ""])
def test_unknown_ai_mode_is_rejected_with_a_clear_error(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(tmp_path, ai_mode=value)
    assert "ai_mode" in str(caught.value)


def test_fake_mode_builds_the_fake_adapters(tmp_path: Path) -> None:
    adapters = build_ai_adapters(make_settings(tmp_path, ai_mode="fake"))
    assert isinstance(adapters.stt, FakeSpeechToText)
    assert isinstance(adapters.voice, FakeVoiceCloner)
    assert isinstance(adapters.lipsync, FakeLipSyncer)


def test_local_mode_builds_real_adapters_without_loading_models(tmp_path: Path) -> None:
    """Construction is cheap and lazy: weights are only touched on first use."""
    adapters = build_ai_adapters(make_settings(tmp_path, ai_mode="local"))
    assert not isinstance(adapters.stt, FakeSpeechToText)
    assert not isinstance(adapters.voice, FakeVoiceCloner)
    assert not isinstance(adapters.lipsync, FakeLipSyncer)
    assert hasattr(adapters, "transliterator")


def test_importing_the_factory_in_fake_mode_does_not_import_torch() -> None:
    code = (
        "import sys;"
        "from vidgen.infrastructure.local_ai.factory import build_ai_adapters;"
        "assert 'torch' not in sys.modules;"
        "assert 'faster_whisper' not in sys.modules;"
        "assert 'transformers' not in sys.modules"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(  # noqa: S603 - fixed argv, no user input
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_local_mode_forces_offline_model_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC8: voter data never leaves the machine; hub libraries must not fetch."""
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    build_ai_adapters(make_settings(tmp_path, ai_mode="local"))
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    # monkeypatch restores nothing for keys set by the code; clean up explicitly.
    monkeypatch.delenv("HF_HUB_OFFLINE")
    monkeypatch.delenv("TRANSFORMERS_OFFLINE")


@pytest.mark.parametrize(
    ("mode", "requested", "expected"),
    [("local", 2, 1), ("local", 8, 1), ("local", 1, 1), ("fake", 2, 2), ("fake", 4, 4)],
)
def test_worker_concurrency_is_one_in_local_mode(
    tmp_path: Path, mode: str, requested: int, expected: int
) -> None:
    settings = make_settings(tmp_path, ai_mode=mode, worker_threads=requested)
    assert effective_worker_threads(settings) == expected


def test_mode_banner_text_names_the_active_mode(tmp_path: Path) -> None:
    assert describe_mode(make_settings(tmp_path, ai_mode="fake")) == "Fake AI: beep stands in"
    assert describe_mode(make_settings(tmp_path, ai_mode="local")) == "Local AI"
