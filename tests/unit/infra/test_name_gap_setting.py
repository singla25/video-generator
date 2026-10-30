"""The ``name_gap_s`` setting: 0.25 s by default, 0 to 1.0 s (DD-34), and its copy into config."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from tests.integration.api.conftest import make_settings
from vidgen.services.render_support import RenderConfig
from vidgen.settings import Settings
from vidgen.worker.runner import render_config

URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_test"


def build(**overrides: Any) -> Settings:
    """Settings with throwaway secrets."""
    values: dict[str, Any] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("x"),
    }
    values.update(overrides)
    return Settings(**values)


def test_name_gap_defaults_to_a_quarter_second(monkeypatch: pytest.MonkeyPatch) -> None:
    """DD-34 positive: the Settings default is 0.25 s."""
    monkeypatch.delenv("VIDGEN_NAME_GAP_S", raising=False)
    assert build().name_gap_s == 0.25


def test_name_gap_reads_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """DD-34 positive: VIDGEN_NAME_GAP_S overrides the default."""
    monkeypatch.setenv("VIDGEN_NAME_GAP_S", "0.5")
    assert build().name_gap_s == 0.5


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_name_gap_accepts_the_inclusive_range_ends(value: float) -> None:
    """DD-34 edge: 0 (no gap) and 1.0 s (the maximum) are accepted."""
    assert build(name_gap_s=value).name_gap_s == value


@pytest.mark.parametrize("value", [-0.1, 1.5, 1.0001])
def test_name_gap_rejects_values_outside_zero_to_one_second(value: float) -> None:
    """DD-34 negative: a negative gap or one above 1.0 s is a configuration error."""
    with pytest.raises(ValidationError, match="name_gap_s"):
        build(name_gap_s=value)


def test_render_config_copies_the_name_gap_from_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DD-34 positive: the worker's render config gets the default 0.25 s."""
    monkeypatch.delenv("VIDGEN_NAME_GAP_S", raising=False)
    assert render_config(make_settings(URL, tmp_path)).name_gap_s == 0.25


def test_render_config_copies_a_changed_name_gap(tmp_path: Path) -> None:
    """DD-34 positive: a configured gap reaches the render config."""
    assert render_config(make_settings(URL, tmp_path, name_gap_s=0.5)).name_gap_s == 0.5


def test_render_config_gap_is_zero_when_not_given() -> None:
    """DD-34 default: a RenderConfig built directly has no gap (output length = template)."""
    assert RenderConfig(creator_entity="Org", pause_s=0.5).name_gap_s == 0.0
