"""The ``ai_backend`` setting selects fake or real adapters (M2 plan G4)."""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from vidgen.settings import Settings


def build(**overrides: Any) -> Settings:
    """Settings with throwaway secrets; reads no environment for ai_backend unless set."""
    values: dict[str, Any] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("x"),
    }
    values.update(overrides)
    return Settings(**values)


def test_ai_backend_defaults_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    """M2-S7-P1."""
    monkeypatch.delenv("VIDGEN_AI_BACKEND", raising=False)
    assert build().ai_backend == "fake"


@pytest.mark.parametrize("value", ["fake", "real"])
def test_ai_backend_accepts_fake_and_real(value: str) -> None:
    """M2-S7-P2."""
    assert build(ai_backend=value).ai_backend == value


def test_ai_backend_reads_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """M2-S7-P3."""
    monkeypatch.setenv("VIDGEN_AI_BACKEND", "real")
    assert build().ai_backend == "real"


@pytest.mark.parametrize("value", ["gpu", "", "REAL", "Fake", " real", "mock", "none"])
def test_ai_backend_rejects_anything_else(value: str) -> None:
    """M2-S7-N1: no silent fallback to fake for a typo."""
    with pytest.raises(ValidationError, match="ai_backend"):
        build(ai_backend=value)
