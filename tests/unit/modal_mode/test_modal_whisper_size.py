"""The Modal app builds its Whisper repo from ``VIDGEN_MODAL_WHISPER_SIZE`` (default medium)."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import pytest

from tests.fixtures.modal_stub import stub_modal
from tests.unit.modal_mode.conftest import APP_FILE

ENV = "VIDGEN_MODAL_WHISPER_SIZE"


def import_app() -> Any:
    """Import the app file under the stub modal and return the module."""
    with stub_modal():
        spec = importlib.util.spec_from_file_location("modal_app_size_under_test", APP_FILE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
    return module


def test_default_repo_is_medium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV, raising=False)
    assert import_app().WHISPER_REPO == "Systran/faster-whisper-medium"


@pytest.mark.parametrize("size", ["small", "medium"])
def test_environment_picks_the_repo(monkeypatch: pytest.MonkeyPatch, size: str) -> None:
    monkeypatch.setenv(ENV, size)
    assert f"Systran/faster-whisper-{size}" == import_app().WHISPER_REPO


@pytest.mark.parametrize("value", ["large", "", "MEDIUM", "../small"])
def test_invalid_size_raises_a_clear_value_error_at_import(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV, value)
    with pytest.raises(ValueError, match="WHISPER_SIZE"):
        import_app()
