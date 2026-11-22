"""``whisper_weights_dir`` and the size passed to the speech-to-text adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.unit.ai_local.conftest import make_settings
from vidgen.infrastructure.fakes import FakeSpeechToText
from vidgen.infrastructure.local_ai.errors import ModelWeightsMissingError
from vidgen.infrastructure.local_ai.factory import build_ai_adapters, whisper_weights_dir


def listing(root: Path) -> list[str]:
    return sorted(p.name for p in root.rglob("*"))


# --- whisper_weights_dir ------------------------------------------------------------------------


def test_small_prefers_the_whisper_small_folder(tmp_path: Path) -> None:
    (tmp_path / "whisper-small").mkdir()
    (tmp_path / "whisper").mkdir()
    assert whisper_weights_dir(tmp_path, "small") == tmp_path / "whisper-small"


def test_small_falls_back_to_the_legacy_whisper_folder(tmp_path: Path) -> None:
    (tmp_path / "whisper").mkdir()
    assert whisper_weights_dir(tmp_path, "small") == tmp_path / "whisper"


def test_small_with_neither_folder_returns_the_legacy_path(tmp_path: Path) -> None:
    assert whisper_weights_dir(tmp_path, "small") == tmp_path / "whisper"


@pytest.mark.parametrize("present", [True, False])
def test_medium_is_always_the_whisper_medium_folder(tmp_path: Path, present: bool) -> None:
    (tmp_path / "whisper").mkdir()  # the legacy folder never stands in for medium
    if present:
        (tmp_path / "whisper-medium").mkdir()
    assert whisper_weights_dir(tmp_path, "medium") == tmp_path / "whisper-medium"


@pytest.mark.parametrize("size", ["large", "", "Small", "tiny"])
def test_unknown_size_raises_value_error(tmp_path: Path, size: str) -> None:
    with pytest.raises(ValueError, match="whisper"):
        whisper_weights_dir(tmp_path, size)


def test_root_with_unicode_and_spaces(tmp_path: Path) -> None:
    root = tmp_path / "मॉडल models ✓"
    (root / "whisper-small").mkdir(parents=True)
    assert whisper_weights_dir(root, "small") == root / "whisper-small"
    assert whisper_weights_dir(root, "medium") == root / "whisper-medium"


@pytest.mark.parametrize("size", ["small", "medium"])
def test_it_never_creates_anything(tmp_path: Path, size: str) -> None:
    (tmp_path / "other").mkdir()
    before = listing(tmp_path)
    whisper_weights_dir(tmp_path, size)
    assert listing(tmp_path) == before


def test_it_does_not_create_a_missing_root(tmp_path: Path) -> None:
    root = tmp_path / "no-such-root"
    whisper_weights_dir(root, "medium")
    assert not root.exists()


# --- build_ai_adapters --------------------------------------------------------------------------


def stt_weights(adapters: Any) -> Path:
    return adapters.stt._model._weights_dir  # type: ignore[no-any-return]


def test_local_default_size_uses_whisper_small_folder(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, ai_mode="local")
    (settings.local_ai_weights_dir / "whisper-small").mkdir(parents=True)
    assert (
        stt_weights(build_ai_adapters(settings)) == settings.local_ai_weights_dir / "whisper-small"
    )


def test_local_small_with_legacy_folder_still_works(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, ai_mode="local", whisper_size="small")
    (settings.local_ai_weights_dir / "whisper").mkdir(parents=True)
    assert stt_weights(build_ai_adapters(settings)) == settings.local_ai_weights_dir / "whisper"


def test_local_medium_uses_whisper_medium_folder(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, ai_mode="local", whisper_size="medium")
    assert (
        stt_weights(build_ai_adapters(settings)) == settings.local_ai_weights_dir / "whisper-medium"
    )


def test_other_adapters_keep_their_folders(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, ai_mode="local", whisper_size="medium")
    adapters = build_ai_adapters(settings)
    assert adapters.voice._model._weights_dir == settings.local_ai_weights_dir / "chatterbox"


def test_fake_mode_ignores_the_size(tmp_path: Path) -> None:
    adapters = build_ai_adapters(make_settings(tmp_path, ai_mode="fake", whisper_size="medium"))
    assert isinstance(adapters.stt, FakeSpeechToText)


@pytest.mark.parametrize("use", ["warm_up", "transcribe"])
def test_missing_medium_folder_gives_a_clear_error_without_the_home_path(
    tmp_path: Path, use: str
) -> None:
    from tests.unit.ai_local.conftest import write_wav

    settings = make_settings(tmp_path, ai_mode="local", whisper_size="medium")
    settings.local_ai_weights_dir.mkdir(parents=True)
    adapters = build_ai_adapters(settings)
    audio = write_wav(tmp_path / "a.wav")
    with pytest.raises(ModelWeightsMissingError) as caught:
        adapters.stt.warm_up() if use == "warm_up" else adapters.stt.transcribe(audio)
    text = str(caught.value)
    assert "whisper-medium" in text
    assert str(tmp_path) not in text
    assert "download" in text.lower()
