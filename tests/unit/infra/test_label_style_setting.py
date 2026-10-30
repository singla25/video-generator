"""The ``label_style`` setting: bubble (default) or band (DD-32). LS-S-*."""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from vidgen.settings import Settings


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


def test_label_style_defaults_to_bubble(monkeypatch: pytest.MonkeyPatch) -> None:
    """LS-S-P1."""
    monkeypatch.delenv("VIDGEN_LABEL_STYLE", raising=False)
    assert build().label_style == "bubble"


@pytest.mark.parametrize("value", ["bubble", "band"])
def test_label_style_accepts_bubble_and_band(value: str) -> None:
    """LS-S-P2."""
    assert build(label_style=value).label_style == value


def test_label_style_reads_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """LS-S-P3."""
    monkeypatch.setenv("VIDGEN_LABEL_STYLE", "band")
    assert build().label_style == "band"


@pytest.mark.parametrize("value", ["", "BAND", "Bubble", " band", "bar", "none", "stripe"])
def test_label_style_rejects_anything_else(value: str) -> None:
    """LS-S-N1: no silent fallback for a typo (the label is a legal disclosure)."""
    with pytest.raises(ValidationError, match="label_style"):
        build(label_style=value)


def test_band_share_is_still_validated_when_the_style_is_bubble() -> None:
    """LS-S-E1: switching style must not open a way to a sub-10 % band setting."""
    with pytest.raises(ValidationError, match="label_band_share"):
        build(label_style="bubble", label_band_share=0.05)
