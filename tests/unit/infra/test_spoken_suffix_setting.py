"""The ``spoken_suffix`` setting (DD-39): default "जी", max 20 characters, and its copy into config.

CONTRACT
  Settings.spoken_suffix: str = "जी", read from VIDGEN_SPOKEN_SUFFIX, max length 20; "" is allowed.
  render_config(settings) copies it into RenderConfig.spoken_suffix, whose default is "".

Test tree IDs: SS-S-* (setting), see docs/test-tree/spoken-suffix.md.
"""

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
ENV = "VIDGEN_SPOKEN_SUFFIX"
DEFAULT_SUFFIX = "जी"  # "जी"


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


# ---- positive -------------------------------------------------------------------------


def test_spoken_suffix_defaults_to_ji(monkeypatch: pytest.MonkeyPatch) -> None:
    """SS-S-P1: with no environment variable, the default is the Devanagari honorific."""
    monkeypatch.delenv(ENV, raising=False)
    assert build().spoken_suffix == DEFAULT_SUFFIX


def test_spoken_suffix_reads_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """SS-S-P2: VIDGEN_SPOKEN_SUFFIX overrides the default."""
    monkeypatch.setenv(ENV, "साहब")  # "साहब"
    assert build().spoken_suffix == "साहब"


def test_spoken_suffix_accepts_a_roman_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """SS-S-P2: the setting is plain text; a Roman honorific is accepted."""
    monkeypatch.setenv(ENV, "Ji")
    assert build().spoken_suffix == "Ji"


def test_render_config_copies_the_default_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SS-S-P3: the worker's render config gets the default suffix."""
    monkeypatch.delenv(ENV, raising=False)
    assert render_config(make_settings(URL, tmp_path)).spoken_suffix == DEFAULT_SUFFIX


def test_render_config_copies_a_changed_suffix(tmp_path: Path) -> None:
    """SS-S-P3: a configured suffix reaches the render config."""
    suffix = "साहब"
    assert render_config(make_settings(URL, tmp_path, spoken_suffix=suffix)).spoken_suffix == suffix


def test_render_config_built_directly_has_no_suffix() -> None:
    """SS-S-P4: a RenderConfig built without the field speaks the name only."""
    assert RenderConfig(creator_entity="Org", pause_s=0.5).spoken_suffix == ""


# ---- negative -------------------------------------------------------------------------


def test_a_suffix_longer_than_twenty_characters_is_rejected() -> None:
    """SS-S-N1: 21 characters is a configuration error that names the setting."""
    with pytest.raises(ValidationError, match="spoken_suffix"):
        build(spoken_suffix="A" * 21)


def test_a_suffix_longer_than_twenty_characters_is_rejected_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SS-S-N1: the same rule applies to the environment variable."""
    monkeypatch.setenv(ENV, "A" * 21)
    with pytest.raises(ValidationError, match="spoken_suffix"):
        build()


# ---- edge -----------------------------------------------------------------------------


def test_an_empty_suffix_is_allowed_and_switches_the_feature_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SS-S-E1: an empty environment value is accepted and kept as ""."""
    monkeypatch.setenv(ENV, "")
    assert build().spoken_suffix == ""


def test_an_empty_suffix_is_copied_into_the_render_config(tmp_path: Path) -> None:
    """SS-S-E1: "" reaches the render config so the voice gets the name only."""
    assert render_config(make_settings(URL, tmp_path, spoken_suffix="")).spoken_suffix == ""


@pytest.mark.parametrize("value", ["A" * 20, "जी" * 10])
def test_a_suffix_of_exactly_twenty_characters_is_accepted(value: str) -> None:
    """SS-S-E2: the maximum length is inclusive."""
    assert build(spoken_suffix=value).spoken_suffix == value


def test_a_suffix_of_nineteen_characters_is_accepted() -> None:
    """SS-S-E2: one below the maximum is accepted too."""
    assert build(spoken_suffix="A" * 19).spoken_suffix == "A" * 19
