"""The ``warm_up_on_start`` setting (T-PROG-BE, item 6): off by default.

CONTRACT
  Settings.warm_up_on_start: bool = False, read from VIDGEN_WARM_UP_ON_START.
"""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from vidgen.settings import Settings

ENV = "VIDGEN_WARM_UP_ON_START"


def build(**overrides: Any) -> Settings:
    """Settings with throwaway secrets (the required fields have no defaults)."""
    values: dict[str, Any] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("x"),
    }
    values.update(overrides)
    return Settings(**values)


def test_warm_up_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """P1: nothing is loaded at worker start unless the operator asks for it."""
    monkeypatch.delenv(ENV, raising=False)
    assert build().warm_up_on_start is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "True"])
def test_truthy_environment_values_turn_warm_up_on(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """P2: the usual boolean spellings enable warm-up."""
    monkeypatch.setenv(ENV, value)
    assert build().warm_up_on_start is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "False"])
def test_falsy_environment_values_keep_warm_up_off(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """N2: explicit falsy values keep it off."""
    monkeypatch.setenv(ENV, value)
    assert build().warm_up_on_start is False


def test_an_invalid_value_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """N1: a value that is not a boolean fails at start-up and names the setting."""
    monkeypatch.setenv(ENV, "maybe")
    with pytest.raises(ValidationError, match="warm_up_on_start"):
        build()


def test_only_the_exact_environment_name_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """E1: a similar but different variable does not switch warm-up on."""
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setenv("VIDGEN_WARM_UP", "true")
    monkeypatch.setenv("WARM_UP_ON_START", "true")
    assert build().warm_up_on_start is False
