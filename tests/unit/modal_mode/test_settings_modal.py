"""AC3: the settings accept the modal mode and name the Modal app."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.unit.ai_local.conftest import make_settings


def test_modal_is_an_accepted_ai_mode(tmp_path: Path) -> None:
    assert make_settings(tmp_path, ai_mode="modal").ai_mode == "modal"


def test_the_modal_app_name_defaults_to_vidgen_ai(tmp_path: Path) -> None:
    assert make_settings(tmp_path).modal_app_name == "vidgen-ai"


def test_the_modal_app_name_is_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDGEN_MODAL_APP_NAME", "my-app")
    assert make_settings(tmp_path).modal_app_name == "my-app"


def test_ai_mode_modal_is_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDGEN_AI_MODE", "modal")
    assert make_settings(tmp_path).ai_mode == "modal"


@pytest.mark.parametrize("mode", ["cloud", "MODAL ", "", "remote"])
def test_an_unknown_ai_mode_is_refused(tmp_path: Path, mode: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, ai_mode=mode)


def test_modal_tokens_are_not_settings_fields(tmp_path: Path) -> None:
    """The tokens stay Modal's own environment variables, never part of Settings (no leak)."""
    names = " ".join(type(make_settings(tmp_path)).model_fields).lower()
    assert "token" not in names
